//+------------------------------------------------------------------+
//| AlphaMining_PortfolioC_9Models_v2.mq5
//| AUTO-GENERATED DETERMINISTICALLY BY scripts/build_ea_portfolio.py
//| Portfolio ID : portfolio_c_9models_v2
//| Core Helpers : sha=bb9ba902c48f
//| Account Mode : MT5 Hedging required
//|
//| Included Models (editable inputs: Enable & Lot only):
//|  1) Alpha005   [alpha] v1.0.0 | magic=5105005 | status=exploratory | sha=ff05fe5b933c
//|  2) Alpha055   [alpha] v1.0.0 | magic=5105055 | status=exploratory | sha=cdd6aee0943f
//|  3) Alpha010   [alpha] v1.0.0 | magic=5105010 | status=exploratory | sha=1bdb5a21e702
//|  4) Heiken     [alpha] v1.0.0 | magic=20260616 | status=exploratory | sha=c6f34f40619c
//|  5) MACross    [alpha] v1.0.0 | magic=20260617 | status=exploratory | sha=f0b9ff1c494c
//|  6) Breakout   [alpha] v1.0.0 | magic=20261130 | status=exploratory | sha=809a9949dd1a
//|  7) EMA4H      [alpha] v1.0.0 | magic=20261140 | status=exploratory | sha=5a3b4312e9f6
//|  8) SessionA   [alpha] v1.0.0 | magic=20261161 | status=exploratory | sha=cd8be5f61dbc
//|  9) SessionB   [alpha] v1.0.0 | magic=20261162 | status=exploratory | sha=99a04a4c80dd
//|
//| DO NOT EDIT DIRECTLY — edit atomic files under models/ and rebuild.
//+------------------------------------------------------------------+
#property strict

#include <Trade/Trade.mqh>

CTrade trade;
datetime g_lastDisableCheck = 0;
#define DISABLE_CHECK_INTERVAL_SECONDS 60


//====================================================================//
// USER INPUTS (Enable / Lot / Account_Lock ONLY)
//====================================================================//

input long Account_Lock = 0; // 0 = no account lock

// alpha005 — Alpha005 — H1 14-Bar Momentum
input bool   Enable_Alpha005 = true;
input double Lot_Alpha005    = 0.10;

// alpha055 — Alpha055 — H1 14-Bar Momentum (Preserved Separate Slot)
input bool   Enable_Alpha055 = true;
input double Lot_Alpha055    = 0.10;

// alpha010 — Alpha010 — H1 90-Bar Momentum
input bool   Enable_Alpha010 = true;
input double Lot_Alpha010    = 0.10;

// heiken_ma_12_26 — Heiken Ashi MA Cross (M15 SMA 12/26)
input bool   Enable_Heiken = true;
input double Lot_Heiken    = 0.01;

// macross_sma_28_101 — MA Cross (M15 SMA 28/101, Long-Only)
input bool   Enable_MACross = true;
input double Lot_MACross    = 0.01;

// donchian_breakout_40_10 — Donchian Breakout (M30 Entry 40 / Exit 10, Long-Only)
input bool   Enable_Breakout = true;
input double Lot_Breakout    = 0.01;

// ema_4h_5_20 — EMA 4H Two-Way (H4 EMA 5/20, Long & Short)
input bool   Enable_EMA4H = true;
input double Lot_EMA4H    = 0.01;

// session_a_22_06 — Session A (Broker 22:00-06:00, Buy inside / Flat outside)
input bool   Enable_SessionA = true;
input double Lot_SessionA    = 0.01;

// session_b_21_04 — Session B (Broker 21:00-04:00, Buy inside / Flat outside)
input bool   Enable_SessionB = true;
input double Lot_SessionB    = 0.01;


//====================================================================//
// SHARED CORE EXECUTION & POSITION HELPERS (MT5 Hedging Account)
// Source: models/mql5_core/execution_helpers.mqh
//
// Market-closed / rollover guard:
//   Observed in MT5 Strategy Tester (00:00-01:05 broker time) that order
//   spam produced retcode=10018 (TRADE_RETCODE_MARKET_CLOSED) on every tick.
//   Every order/close helper below now:
//     1) refuses to send while g_marketRetryAfter is in the future, and
//     2) arms a MARKET_CLOSED_COOLDOWN_SECONDS cooldown on retcode
//        10018 (market closed) / 10017 (trade disabled) / SYMBOL_TRADE_MODE_DISABLED.
//====================================================================//

#define MARKET_CLOSED_COOLDOWN_SECONDS 60

datetime g_marketRetryAfter = 0;

bool IsHedgingAccount()
{
   return AccountInfoInteger(ACCOUNT_MARGIN_MODE)
          == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING;
}

double VolumeStep()
{
   double value = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(value <= 0.0)
      value = 0.01;
   return value;
}

double MinVolume()
{
   double value = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   if(value <= 0.0)
      value = 0.01;
   return value;
}

double MaxVolume()
{
   double value = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(value <= 0.0)
      value = 100.0;
   return value;
}

int VolumeDigits()
{
   double step = VolumeStep();

   if(step >= 1.0)   return 0;
   if(step >= 0.1)   return 1;
   if(step >= 0.01)  return 2;
   if(step >= 0.001) return 3;

   return 4;
}

// 0 lot = disabled by lot
double NormalizeLots(double lots)
{
   if(lots <= 0.0)
      return 0.0;

   double step = VolumeStep();
   double minv = MinVolume();
   double maxv = MaxVolume();

   lots = MathRound(lots / step) * step;

   if(lots < minv)
      return 0.0;

   if(lots > maxv)
      lots = maxv;

   return NormalizeDouble(lots, VolumeDigits());
}

bool IsNewBarForTimeframe(ENUM_TIMEFRAMES tf, datetime &lastBarTime)
{
   datetime t = iTime(_Symbol, tf, 0);

   if(t <= 0)
      return false;

   if(t == lastBarTime)
      return false;

   lastBarTime = t;
   return true;
}

//====================================================================//
// MARKET-OPEN / ROLLOVER GUARD
//====================================================================//

bool IsMarketTradeAllowed()
{
   datetime now = TimeCurrent();

   if(g_marketRetryAfter > 0 && now < g_marketRetryAfter)
      return false;

   long mode = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   if(mode == SYMBOL_TRADE_MODE_DISABLED)
   {
      g_marketRetryAfter = now + MARKET_CLOSED_COOLDOWN_SECONDS;
      return false;
   }

   return true;
}

void NoteTradeResult(uint retcode)
{
   if(retcode == TRADE_RETCODE_MARKET_CLOSED ||
      retcode == TRADE_RETCODE_TRADE_DISABLED)
   {
      g_marketRetryAfter = TimeCurrent() + MARKET_CLOSED_COOLDOWN_SECONDS;
   }
}

//====================================================================//
// POSITION HELPERS
//====================================================================//

bool FindPositionByMagicAndType(long magic,
                                long posType,
                                ulong &ticket,
                                double &volume)
{
   ticket = 0;
   volume = 0.0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong currentTicket = PositionGetTicket(i);

      if(currentTicket == 0)
         continue;

      if(!PositionSelectByTicket(currentTicket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;

      if((long)PositionGetInteger(POSITION_MAGIC) != magic)
         continue;

      if((long)PositionGetInteger(POSITION_TYPE) != posType)
         continue;

      ticket = currentTicket;
      volume = PositionGetDouble(POSITION_VOLUME);
      return true;
   }

   return false;
}

bool FindBuyPositionByMagic(long magic,
                            ulong &ticket,
                            double &volume)
{
   return FindPositionByMagicAndType(magic, POSITION_TYPE_BUY, ticket, volume);
}

int CountPositionsByMagic(long magic)
{
   int count = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);

      if(ticket == 0)
         continue;

      if(!PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;

      if((long)PositionGetInteger(POSITION_MAGIC) != magic)
         continue;

      count++;
   }

   return count;
}

int CountPositionsByMagicAndType(long magic, long posType)
{
   int count = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);

      if(ticket == 0)
         continue;

      if(!PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;

      if((long)PositionGetInteger(POSITION_MAGIC) != magic)
         continue;

      if((long)PositionGetInteger(POSITION_TYPE) != posType)
         continue;

      count++;
   }

   return count;
}

//====================================================================//
// ORDER HELPERS (all guarded by the market-open cooldown)
//====================================================================//

bool OpenBuyByMagic(long magic,
                    double lots,
                    int deviationPoints,
                    string label)
{
   lots = NormalizeLots(lots);

   if(lots <= 0.0)
      return false;

   if(!IsMarketTradeAllowed())
      return false;

   trade.SetExpertMagicNumber(magic);
   trade.SetDeviationInPoints(deviationPoints);

   bool ok = trade.Buy(
      lots,
      _Symbol,
      0.0,
      0.0,
      0.0,
      label
   );

   if(!ok)
   {
      NoteTradeResult(trade.ResultRetcode());
      Print(
         label,
         " BUY failed | retcode=",
         trade.ResultRetcode(),
         " | ",
         trade.ResultRetcodeDescription()
      );
   }

   return ok;
}

bool OpenSellByMagic(long magic,
                     double lots,
                     int deviationPoints,
                     string label)
{
   lots = NormalizeLots(lots);

   if(lots <= 0.0)
      return false;

   if(!IsMarketTradeAllowed())
      return false;

   trade.SetExpertMagicNumber(magic);
   trade.SetDeviationInPoints(deviationPoints);

   bool ok = trade.Sell(
      lots,
      _Symbol,
      0.0,
      0.0,
      0.0,
      label
   );

   if(!ok)
   {
      NoteTradeResult(trade.ResultRetcode());
      Print(
         label,
         " SELL failed | retcode=",
         trade.ResultRetcode(),
         " | ",
         trade.ResultRetcodeDescription()
      );
   }

   return ok;
}

bool OpenPctSlTpOrderByMagic(long magic,
                             double lots,
                             ENUM_ORDER_TYPE orderType,
                             double slPct,
                             double tpPct,
                             int maxSpreadPoints,
                             int deviationPoints,
                             string comment,
                             string label)
{
   lots = NormalizeLots(lots);
   if(lots <= 0.0)
      return false;

   if(!IsMarketTradeAllowed())
      return false;

   if(maxSpreadPoints > 0)
   {
      long spreadPts = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
      if(spreadPts > maxSpreadPoints)
         return false;
   }

   double point      = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double ask        = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid        = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double stopsLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * point;

   double price = (orderType == ORDER_TYPE_BUY) ? ask : bid;
   if(price <= 0.0)
      return false;

   double sl = 0.0;
   double tp = 0.0;

   if(slPct > 0.0)
   {
      double slDist = MathMax(price * (slPct / 100.0), stopsLevel);
      sl = (orderType == ORDER_TYPE_BUY)
           ? NormalizeDouble(MathMax(point, price - slDist), _Digits)
           : NormalizeDouble(price + slDist, _Digits);
   }

   if(tpPct > 0.0)
   {
      double tpDist = MathMax(price * (tpPct / 100.0), stopsLevel);
      tp = (orderType == ORDER_TYPE_BUY)
           ? NormalizeDouble(price + tpDist, _Digits)
           : NormalizeDouble(MathMax(point, price - tpDist), _Digits);
   }

   trade.SetExpertMagicNumber(magic);
   trade.SetDeviationInPoints(deviationPoints);

   bool ok = false;
   if(orderType == ORDER_TYPE_BUY)
      ok = trade.Buy(lots, _Symbol, price, sl, tp, comment);
   else if(orderType == ORDER_TYPE_SELL)
      ok = trade.Sell(lots, _Symbol, price, sl, tp, comment);

   if(!ok)
   {
      NoteTradeResult(trade.ResultRetcode());
      Print(
         label,
         (orderType == ORDER_TYPE_BUY ? " BUY" : " SELL"),
         " failed | retcode=",
         trade.ResultRetcode(),
         " | ",
         trade.ResultRetcodeDescription()
      );
   }

   return ok;
}

bool CloseOneBuyPositionByMagic(long magic,
                                int deviationPoints,
                                string label)
{
   ulong ticket = 0;
   double volume = 0.0;

   if(!FindBuyPositionByMagic(magic, ticket, volume))
      return true;

   if(!IsMarketTradeAllowed())
      return false;

   trade.SetExpertMagicNumber(magic);
   trade.SetDeviationInPoints(deviationPoints);

   bool ok = trade.PositionClose(ticket);

   if(!ok)
   {
      NoteTradeResult(trade.ResultRetcode());
      Print(
         label,
         " CLOSE failed | ticket=",
         ticket,
         " | retcode=",
         trade.ResultRetcode(),
         " | ",
         trade.ResultRetcodeDescription()
      );
   }

   return ok;
}

bool ClosePositionsByMagicAndType(long magic,
                                  long posType,
                                  int deviationPoints,
                                  string label)
{
   bool allClosed = true;

   if(CountPositionsByMagicAndType(magic, posType) > 0 && !IsMarketTradeAllowed())
      return false;

   trade.SetExpertMagicNumber(magic);
   trade.SetDeviationInPoints(deviationPoints);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);

      if(ticket == 0)
         continue;

      if(!PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;

      if((long)PositionGetInteger(POSITION_MAGIC) != magic)
         continue;

      if((long)PositionGetInteger(POSITION_TYPE) != posType)
         continue;

      bool ok = trade.PositionClose(ticket);

      if(!ok)
      {
         allClosed = false;
         NoteTradeResult(trade.ResultRetcode());
         Print(
            label,
            " CLOSE failed | ticket=",
            ticket,
            " | retcode=",
            trade.ResultRetcode(),
            " | ",
            trade.ResultRetcodeDescription()
         );
         if(!IsMarketTradeAllowed())
            break;
      }
   }

   return allClosed;
}

void CloseAllPositionsByMagic(long magic,
                              int deviationPoints,
                              string label)
{
   if(CountPositionsByMagic(magic) > 0 && !IsMarketTradeAllowed())
      return;

   trade.SetExpertMagicNumber(magic);
   trade.SetDeviationInPoints(deviationPoints);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);

      if(ticket == 0)
         continue;

      if(!PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;

      if((long)PositionGetInteger(POSITION_MAGIC) != magic)
         continue;

      bool ok = trade.PositionClose(ticket);

      if(!ok)
      {
         NoteTradeResult(trade.ResultRetcode());
         Print(
            label,
            " CLOSE failed | ticket=",
            ticket,
            " | retcode=",
            trade.ResultRetcode(),
            " | ",
            trade.ResultRetcodeDescription()
         );
         if(!IsMarketTradeAllowed())
            break;
      }
   }
}

bool SyncLongTrendModel(bool enabled,
                        bool signal,
                        long magic,
                        double targetLots,
                        int deviationPoints,
                        string label)
{
   if(!enabled)
      return true;

   targetLots = NormalizeLots(targetLots);

   if(targetLots <= 0.0)
      return true;

   ulong ticket = 0;
   double currentLots = 0.0;

   bool hasPosition =
      FindBuyPositionByMagic(
         magic,
         ticket,
         currentLots
      );

   // Signal OFF -> close
   if(!signal)
   {
      if(hasPosition)
      {
         return CloseOneBuyPositionByMagic(
            magic,
            deviationPoints,
            label
         );
      }

      return true;
   }

   // Signal ON -> open if flat
   if(!hasPosition)
   {
      return OpenBuyByMagic(
         magic,
         targetLots,
         deviationPoints,
         label
      );
   }

   // Lot changed -> resize this model only
   double step = VolumeStep();

   if(MathAbs(currentLots - targetLots) >= step / 2.0)
   {
      if(!CloseOneBuyPositionByMagic(
            magic,
            deviationPoints,
            label))
         return false;

      return OpenBuyByMagic(
         magic,
         targetLots,
         deviationPoints,
         label
      );
   }

   return true;
}


//====================================================================//
// MODEL: alpha005 (H1 14-bar momentum, Long-Only)
// Magic: 5105005 | Prefix: Alpha005
//====================================================================//

#define ALPHA005_TF               PERIOD_H1
#define ALPHA005_LOOKBACK_SHIFT   15
#define ALPHA005_MIN_BARS         100
#define ALPHA005_DEVIATION_POINTS 20
#define MAGIC_ALPHA005            5105005

datetime g_lastBar_Alpha005 = 0;

bool Alpha005_Signal()
{
   double c1  = iClose(_Symbol, ALPHA005_TF, 1);
   double c15 = iClose(_Symbol, ALPHA005_TF, ALPHA005_LOOKBACK_SHIFT);

   return (
      c1 > 0.0 &&
      c15 > 0.0 &&
      c1 > c15
   );
}

void Init_Alpha005()
{
   g_lastBar_Alpha005 = iTime(_Symbol, ALPHA005_TF, 0);
}

void LogConfig_Alpha005()
{
   Print("Alpha005 FIXED | TF=H1 | Rule=Close[1]>Close[15] | Magic=", MAGIC_ALPHA005);
}

void EnforceDisabled_Alpha005(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_ALPHA005,
         ALPHA005_DEVIATION_POINTS,
         "Alpha005"
      );
   }
}

void Process_Alpha005(bool enabled, double lots)
{
   if(!IsNewBarForTimeframe(ALPHA005_TF, g_lastBar_Alpha005))
      return;

   if(!enabled)
      return;

   if(Bars(_Symbol, ALPHA005_TF) < ALPHA005_MIN_BARS)
   {
      Print("Alpha005 waiting for at least 100 H1 bars.");
      return;
   }

   SyncLongTrendModel(
      true,
      Alpha005_Signal(),
      MAGIC_ALPHA005,
      lots,
      ALPHA005_DEVIATION_POINTS,
      "Alpha005"
   );
}


//====================================================================//
// MODEL: alpha055 (H1 14-bar momentum, Preserved Separate Slot)
// Magic: 5105055 | Prefix: Alpha055
//====================================================================//

#define ALPHA055_TF               PERIOD_H1
#define ALPHA055_LOOKBACK_SHIFT   15
#define ALPHA055_MIN_BARS         100
#define ALPHA055_DEVIATION_POINTS 20
#define MAGIC_ALPHA055            5105055

datetime g_lastBar_Alpha055 = 0;

bool Alpha055_Signal()
{
   // Kept exactly as supplied: same binary sign as Alpha005 in this adaptation.
   double c1  = iClose(_Symbol, ALPHA055_TF, 1);
   double c15 = iClose(_Symbol, ALPHA055_TF, ALPHA055_LOOKBACK_SHIFT);

   return (
      c1 > 0.0 &&
      c15 > 0.0 &&
      c1 > c15
   );
}

void Init_Alpha055()
{
   g_lastBar_Alpha055 = iTime(_Symbol, ALPHA055_TF, 0);
}

void LogConfig_Alpha055()
{
   Print("Alpha055 FIXED | TF=H1 | Rule=Close[1]>Close[15] | Magic=", MAGIC_ALPHA055);
}

void EnforceDisabled_Alpha055(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_ALPHA055,
         ALPHA055_DEVIATION_POINTS,
         "Alpha055"
      );
   }
}

void Process_Alpha055(bool enabled, double lots)
{
   if(!IsNewBarForTimeframe(ALPHA055_TF, g_lastBar_Alpha055))
      return;

   if(!enabled)
      return;

   if(Bars(_Symbol, ALPHA055_TF) < ALPHA055_MIN_BARS)
   {
      Print("Alpha055 waiting for at least 100 H1 bars.");
      return;
   }

   SyncLongTrendModel(
      true,
      Alpha055_Signal(),
      MAGIC_ALPHA055,
      lots,
      ALPHA055_DEVIATION_POINTS,
      "Alpha055"
   );
}


//====================================================================//
// MODEL: alpha010 (H1 90-bar momentum, Long-Only)
// Magic: 5105010 | Prefix: Alpha010
//====================================================================//

#define ALPHA010_TF               PERIOD_H1
#define ALPHA010_LOOKBACK_SHIFT   91
#define ALPHA010_MIN_BARS         100
#define ALPHA010_DEVIATION_POINTS 20
#define MAGIC_ALPHA010            5105010

datetime g_lastBar_Alpha010 = 0;

bool Alpha010_Signal()
{
   double c1  = iClose(_Symbol, ALPHA010_TF, 1);
   double c91 = iClose(_Symbol, ALPHA010_TF, ALPHA010_LOOKBACK_SHIFT);

   return (
      c1 > 0.0 &&
      c91 > 0.0 &&
      c1 > c91
   );
}

void Init_Alpha010()
{
   g_lastBar_Alpha010 = iTime(_Symbol, ALPHA010_TF, 0);
}

void LogConfig_Alpha010()
{
   Print("Alpha010 FIXED | TF=H1 | Rule=Close[1]>Close[91] | Magic=", MAGIC_ALPHA010);
}

void EnforceDisabled_Alpha010(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_ALPHA010,
         ALPHA010_DEVIATION_POINTS,
         "Alpha010"
      );
   }
}

void Process_Alpha010(bool enabled, double lots)
{
   if(!IsNewBarForTimeframe(ALPHA010_TF, g_lastBar_Alpha010))
      return;

   if(!enabled)
      return;

   if(Bars(_Symbol, ALPHA010_TF) < ALPHA010_MIN_BARS)
   {
      Print("Alpha010 waiting for at least 100 H1 bars.");
      return;
   }

   SyncLongTrendModel(
      true,
      Alpha010_Signal(),
      MAGIC_ALPHA010,
      lots,
      ALPHA010_DEVIATION_POINTS,
      "Alpha010"
   );
}


//====================================================================//
// MODEL: heiken_ma_12_26 (FIXED: M15 / HA Close / SMA 12-26)
// Magic: 20260616 | Prefix: Heiken
//====================================================================//

#define HEIKEN_TF                PERIOD_M15
#define HEIKEN_MAX_SPREAD_POINTS 1000
#define HEIKEN_FAST_MA           12
#define HEIKEN_SLOW_MA           26
#define HEIKEN_DEVIATION_POINTS  30
#define HEIKEN_STOP_THURSDAY     true
#define HEIKEN_STOP_SUNDAY       false
#define MAGIC_HEIKEN             20260616

ENUM_MA_METHOD     g_haMAMethod_Heiken     = MODE_SMA;
ENUM_APPLIED_PRICE g_haAppliedPrice_Heiken = PRICE_CLOSE;
datetime           g_lastBar_Heiken        = 0;

bool Heiken_SpreadOK()
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(ask <= 0.0 || bid <= 0.0)
      return false;

   double spreadPoints = (ask - bid) / _Point;

   return (
      spreadPoints <= HEIKEN_MAX_SPREAD_POINTS
   );
}

bool Heiken_TradingDayAllowed()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);

   if(HEIKEN_STOP_SUNDAY && dt.day_of_week == 0)
      return false;

   if(HEIKEN_STOP_THURSDAY && dt.day_of_week == 4)
      return false;

   return true;
}

double Heiken_GetAppliedPrice(double haOpen,
                              double haHigh,
                              double haLow,
                              double haClose)
{
   switch(g_haAppliedPrice_Heiken)
   {
      case PRICE_OPEN:
         return haOpen;

      case PRICE_HIGH:
         return haHigh;

      case PRICE_LOW:
         return haLow;

      case PRICE_MEDIAN:
         return (haHigh + haLow) / 2.0;

      case PRICE_TYPICAL:
         return (haHigh + haLow + haClose) / 3.0;

      case PRICE_WEIGHTED:
         return (haHigh + haLow + 2.0 * haClose) / 4.0;

      case PRICE_CLOSE:
      default:
         return haClose;
   }
}

bool Heiken_BuildSeries(double &haOpenArr[],
                        double &haHighArr[],
                        double &haLowArr[],
                        double &haCloseArr[],
                        double &haPriceArr[],
                        int &closedIndex,
                        int minimumBarsRequired)
{
   int barsAvailable = Bars(_Symbol, HEIKEN_TF);

   if(barsAvailable < minimumBarsRequired)
      return false;

   int requestedBars =
      minimumBarsRequired * 10 + 100;

   if(requestedBars < 1000)
      requestedBars = 1000;

   if(requestedBars > barsAvailable)
      requestedBars = barsAvailable;

   MqlRates rates[];
   ArraySetAsSeries(rates, false);

   int copied = CopyRates(
      _Symbol,
      HEIKEN_TF,
      0,
      requestedBars,
      rates
   );

   if(copied < minimumBarsRequired)
      return false;

   ArrayResize(haOpenArr,  copied);
   ArrayResize(haHighArr,  copied);
   ArrayResize(haLowArr,   copied);
   ArrayResize(haCloseArr, copied);
   ArrayResize(haPriceArr, copied);

   ArraySetAsSeries(haOpenArr,  false);
   ArraySetAsSeries(haHighArr,  false);
   ArraySetAsSeries(haLowArr,   false);
   ArraySetAsSeries(haCloseArr, false);
   ArraySetAsSeries(haPriceArr, false);

   double prevHAOpen  = 0.0;
   double prevHAClose = 0.0;

   for(int i = 0; i < copied; i++)
   {
      double haClose =
         (
            rates[i].open +
            rates[i].high +
            rates[i].low +
            rates[i].close
         ) / 4.0;

      double haOpen;

      if(i == 0)
      {
         haOpen =
            (rates[i].open + rates[i].close)
            / 2.0;
      }
      else
      {
         haOpen =
            (prevHAOpen + prevHAClose)
            / 2.0;
      }

      double haHigh =
         MathMax(
            rates[i].high,
            MathMax(haOpen, haClose)
         );

      double haLow =
         MathMin(
            rates[i].low,
            MathMin(haOpen, haClose)
         );

      haOpenArr[i]  = haOpen;
      haHighArr[i]  = haHigh;
      haLowArr[i]   = haLow;
      haCloseArr[i] = haClose;

      haPriceArr[i] =
         Heiken_GetAppliedPrice(
            haOpen,
            haHigh,
            haLow,
            haClose
         );

      prevHAOpen  = haOpen;
      prevHAClose = haClose;
   }

   // Latest fully closed candle
   closedIndex = copied - 2;

   return (closedIndex >= 1);
}

bool Heiken_CalculateMAAt(const double &values[],
                          int index,
                          int period,
                          ENUM_MA_METHOD method,
                          double &result)
{
   if(period <= 0 ||
      index < period - 1)
      return false;

   if(method == MODE_SMA)
   {
      double sum = 0.0;
      int first = index - period + 1;

      for(int i = first; i <= index; i++)
         sum += values[i];

      result = sum / period;
      return true;
   }

   if(method == MODE_LWMA)
   {
      double weightedSum = 0.0;
      double weightTotal = 0.0;
      int first = index - period + 1;
      int weight = 1;

      for(int i = first;
          i <= index;
          i++, weight++)
      {
         weightedSum += values[i] * weight;
         weightTotal += weight;
      }

      if(weightTotal <= 0.0)
         return false;

      result = weightedSum / weightTotal;
      return true;
   }

   double seed = 0.0;

   for(int i = 0; i < period; i++)
      seed += values[i];

   double ma = seed / period;

   if(index == period - 1)
   {
      result = ma;
      return true;
   }

   if(method == MODE_EMA)
   {
      double alpha =
         2.0 / (period + 1.0);

      for(int i = period;
          i <= index;
          i++)
      {
         ma =
            alpha * values[i] +
            (1.0 - alpha) * ma;
      }

      result = ma;
      return true;
   }

   if(method == MODE_SMMA)
   {
      for(int i = period;
          i <= index;
          i++)
      {
         ma =
            (
               ma * (period - 1) +
               values[i]
            ) / period;
      }

      result = ma;
      return true;
   }

   return false;
}

bool Heiken_GetMAValues(double &fastClosed,
                        double &fastPrev,
                        double &slowClosed,
                        double &slowPrev)
{
   double haOpenArr[];
   double haHighArr[];
   double haLowArr[];
   double haCloseArr[];
   double haPriceArr[];

   int closedIndex = -1;

   int minimumBarsRequired =
      HEIKEN_SLOW_MA + 3;

   if(!Heiken_BuildSeries(
         haOpenArr,
         haHighArr,
         haLowArr,
         haCloseArr,
         haPriceArr,
         closedIndex,
         minimumBarsRequired))
      return false;

   int prevIndex = closedIndex - 1;

   if(!Heiken_CalculateMAAt(
         haPriceArr,
         closedIndex,
         HEIKEN_FAST_MA,
         g_haMAMethod_Heiken,
         fastClosed))
      return false;

   if(!Heiken_CalculateMAAt(
         haPriceArr,
         prevIndex,
         HEIKEN_FAST_MA,
         g_haMAMethod_Heiken,
         fastPrev))
      return false;

   if(!Heiken_CalculateMAAt(
         haPriceArr,
         closedIndex,
         HEIKEN_SLOW_MA,
         g_haMAMethod_Heiken,
         slowClosed))
      return false;

   if(!Heiken_CalculateMAAt(
         haPriceArr,
         prevIndex,
         HEIKEN_SLOW_MA,
         g_haMAMethod_Heiken,
         slowPrev))
      return false;

   return true;
}

bool Heiken_IsCrossUp(double fastClosed,
                      double fastPrev,
                      double slowClosed,
                      double slowPrev)
{
   return (
      fastPrev <= slowPrev &&
      fastClosed > slowClosed
   );
}

bool Heiken_IsCrossDown(double fastClosed,
                        double fastPrev,
                        double slowClosed,
                        double slowPrev)
{
   return (
      fastPrev >= slowPrev &&
      fastClosed < slowClosed
   );
}

void Init_Heiken()
{
   g_lastBar_Heiken = iTime(_Symbol, HEIKEN_TF, 0);
}

void LogConfig_Heiken()
{
   Print(
      "Heiken FIXED | TF=M15 | Fast=12 | Slow=26 | MaxSpread=1000 | Magic=",
      MAGIC_HEIKEN
   );
}

void EnforceDisabled_Heiken(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_HEIKEN,
         HEIKEN_DEVIATION_POINTS,
         "Heiken"
      );
   }
}

void Process_Heiken(bool enabled, double lots)
{
   if(!IsNewBarForTimeframe(HEIKEN_TF, g_lastBar_Heiken))
      return;

   if(!enabled)
      return;

   double fastClosed = 0.0;
   double fastPrev   = 0.0;
   double slowClosed = 0.0;
   double slowPrev   = 0.0;

   if(!Heiken_GetMAValues(
         fastClosed,
         fastPrev,
         slowClosed,
         slowPrev))
   {
      Print("Heiken MA calculation failed or insufficient data.");
      return;
   }

   bool crossUp =
      Heiken_IsCrossUp(
         fastClosed,
         fastPrev,
         slowClosed,
         slowPrev
      );

   bool crossDown =
      Heiken_IsCrossDown(
         fastClosed,
         fastPrev,
         slowClosed,
         slowPrev
      );

   if(crossDown)
   {
      CloseAllPositionsByMagic(
         MAGIC_HEIKEN,
         HEIKEN_DEVIATION_POINTS,
         "Heiken"
      );
      return;
   }

   if(crossUp)
   {
      double normLot = NormalizeLots(lots);
      if(normLot <= 0.0)
         return;

      if(!Heiken_TradingDayAllowed())
         return;

      if(!Heiken_SpreadOK())
         return;

      if(CountPositionsByMagic(MAGIC_HEIKEN) > 0)
         return;

      OpenBuyByMagic(
         MAGIC_HEIKEN,
         normLot,
         HEIKEN_DEVIATION_POINTS,
         "Heiken_MA_12_26"
      );
   }
}


//====================================================================//
// MODEL: macross_sma_28_101 (FIXED: M15 / SMA 28 vs 101 Close / Long-Only)
// Magic: 20260617 | Prefix: MACross
//====================================================================//

#define MACROSS_TF                 PERIOD_M15
#define MACROSS_FAST_PERIOD        28
#define MACROSS_SLOW_PERIOD        101
#define MACROSS_MAX_SPREAD_POINTS  1000
#define MACROSS_DEVIATION_POINTS   30
#define MACROSS_STOP_THURSDAY      false
#define MACROSS_STOP_SUNDAY        false
#define MAGIC_MACROSS              20260617

ENUM_MA_METHOD     g_maMethod_MACross       = MODE_SMA;
ENUM_APPLIED_PRICE g_maAppliedPrice_MACross = PRICE_CLOSE;
datetime           g_lastBar_MACross        = 0;
int                g_fastHandle_MACross     = INVALID_HANDLE;
int                g_slowHandle_MACross     = INVALID_HANDLE;

bool MACross_SpreadOK()
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(ask <= 0.0 || bid <= 0.0)
      return false;

   double spreadPoints = (ask - bid) / _Point;

   return (spreadPoints <= MACROSS_MAX_SPREAD_POINTS);
}

bool MACross_TradingDayAllowed()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);

   if(MACROSS_STOP_SUNDAY && dt.day_of_week == 0)
      return false;

   if(MACROSS_STOP_THURSDAY && dt.day_of_week == 4)
      return false;

   return true;
}

bool MACross_GetValues(double &fastClosed,
                       double &fastPrev,
                       double &slowClosed,
                       double &slowPrev)
{
   if(g_fastHandle_MACross == INVALID_HANDLE ||
      g_slowHandle_MACross == INVALID_HANDLE)
      return false;

   double fastBuffer[];
   double slowBuffer[];

   ArraySetAsSeries(fastBuffer, true);
   ArraySetAsSeries(slowBuffer, true);

   // shift 1 = latest closed bar, shift 2 = previous closed bar (zero lookahead)
   int fastCopied = CopyBuffer(g_fastHandle_MACross, 0, 1, 2, fastBuffer);
   int slowCopied = CopyBuffer(g_slowHandle_MACross, 0, 1, 2, slowBuffer);

   if(fastCopied != 2 || slowCopied != 2)
      return false;

   fastClosed = fastBuffer[0];
   fastPrev   = fastBuffer[1];
   slowClosed = slowBuffer[0];
   slowPrev   = slowBuffer[1];

   if(fastClosed == EMPTY_VALUE || fastPrev == EMPTY_VALUE ||
      slowClosed == EMPTY_VALUE || slowPrev == EMPTY_VALUE)
      return false;

   return true;
}

void Init_MACross()
{
   g_lastBar_MACross = iTime(_Symbol, MACROSS_TF, 0);

   g_fastHandle_MACross = iMA(_Symbol, MACROSS_TF, MACROSS_FAST_PERIOD, 0,
                              g_maMethod_MACross, g_maAppliedPrice_MACross);
   g_slowHandle_MACross = iMA(_Symbol, MACROSS_TF, MACROSS_SLOW_PERIOD, 0,
                              g_maMethod_MACross, g_maAppliedPrice_MACross);

   if(g_fastHandle_MACross == INVALID_HANDLE ||
      g_slowHandle_MACross == INVALID_HANDLE)
   {
      Print("MACross failed to create SMA handles. Error=", GetLastError());
   }
}

void LogConfig_MACross()
{
   Print(
      "MACross FIXED | TF=M15 | Fast=28 | Slow=101 | MaxSpread=1000 | Magic=",
      MAGIC_MACROSS
   );
}

void EnforceDisabled_MACross(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_MACROSS,
         MACROSS_DEVIATION_POINTS,
         "MACross"
      );
   }
}

void Process_MACross(bool enabled, double lots)
{
   if(!IsNewBarForTimeframe(MACROSS_TF, g_lastBar_MACross))
      return;

   if(!enabled)
      return;

   double fastClosed = 0.0;
   double fastPrev   = 0.0;
   double slowClosed = 0.0;
   double slowPrev   = 0.0;

   if(!MACross_GetValues(fastClosed, fastPrev, slowClosed, slowPrev))
   {
      Print("MACross calculation failed or insufficient data.");
      return;
   }

   bool crossUp   = (fastPrev <= slowPrev && fastClosed > slowClosed);
   bool crossDown = (fastPrev >= slowPrev && fastClosed < slowClosed);

   if(crossDown)
   {
      CloseAllPositionsByMagic(
         MAGIC_MACROSS,
         MACROSS_DEVIATION_POINTS,
         "MACross"
      );
      return;
   }

   if(crossUp)
   {
      double normLot = NormalizeLots(lots);
      if(normLot <= 0.0)
         return;

      if(!MACross_TradingDayAllowed())
         return;

      if(!MACross_SpreadOK())
         return;

      if(CountPositionsByMagic(MAGIC_MACROSS) > 0)
         return;

      OpenBuyByMagic(
         MAGIC_MACROSS,
         normLot,
         MACROSS_DEVIATION_POINTS,
         "MACross_28_101"
      );
   }
}


//====================================================================//
// MODEL: donchian_breakout_40_10 (FIXED: M30 / Entry=40 / Exit=10 / Long-Only)
// Magic: 20261130 | Prefix: Breakout
//====================================================================//

#define BREAKOUT_TF                PERIOD_M30
#define BREAKOUT_ENTRY_BARS        40
#define BREAKOUT_EXIT_BARS         10
#define BREAKOUT_ENABLE_BUY        true
#define BREAKOUT_ENABLE_SELL       false
#define BREAKOUT_DEVIATION_POINTS  30
#define MAGIC_BREAKOUT             20261130

datetime g_lastBar_Breakout = 0;

void Init_Breakout()
{
   g_lastBar_Breakout = iTime(_Symbol, BREAKOUT_TF, 0);
}

void LogConfig_Breakout()
{
   Print(
      "Breakout FIXED | TF=M30 | Entry=40 | Exit=10 | Buy=true | Sell=false | Magic=",
      MAGIC_BREAKOUT
   );
}

void EnforceDisabled_Breakout(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_BREAKOUT,
         BREAKOUT_DEVIATION_POINTS,
         "Breakout"
      );
   }
}

void Process_Breakout(bool enabled, double lots)
{
   if(!IsNewBarForTimeframe(BREAKOUT_TF, g_lastBar_Breakout))
      return;

   if(!enabled)
      return;

   if(Bars(_Symbol, BREAKOUT_TF) < BREAKOUT_ENTRY_BARS + 3)
      return;

   // Latest fully closed bar (shift = 1)
   double close1 = iClose(_Symbol, BREAKOUT_TF, 1);
   if(close1 <= 0.0)
      return;

   // Entry channel (shift 2 .. EntryBars+1) and exit channel (shift 2 .. ExitBars+1)
   int idxEntryHigh = iHighest(_Symbol, BREAKOUT_TF, MODE_HIGH, BREAKOUT_ENTRY_BARS, 2);
   int idxEntryLow  = iLowest (_Symbol, BREAKOUT_TF, MODE_LOW,  BREAKOUT_ENTRY_BARS, 2);
   int idxExitLow   = iLowest (_Symbol, BREAKOUT_TF, MODE_LOW,  BREAKOUT_EXIT_BARS,  2);
   int idxExitHigh  = iHighest(_Symbol, BREAKOUT_TF, MODE_HIGH, BREAKOUT_EXIT_BARS,  2);

   if(idxEntryHigh < 0 || idxEntryLow < 0 || idxExitLow < 0 || idxExitHigh < 0)
      return;

   double entryHigh = iHigh(_Symbol, BREAKOUT_TF, idxEntryHigh);
   double entryLow  = iLow (_Symbol, BREAKOUT_TF, idxEntryLow);
   double exitLow   = iLow (_Symbol, BREAKOUT_TF, idxExitLow);
   double exitHigh  = iHigh(_Symbol, BREAKOUT_TF, idxExitHigh);

   // 1. Exit conditions first
   if(CountPositionsByMagicAndType(MAGIC_BREAKOUT, POSITION_TYPE_BUY) > 0 && close1 < exitLow)
   {
      ClosePositionsByMagicAndType(
         MAGIC_BREAKOUT,
         POSITION_TYPE_BUY,
         BREAKOUT_DEVIATION_POINTS,
         "Breakout"
      );
   }

   if(CountPositionsByMagicAndType(MAGIC_BREAKOUT, POSITION_TYPE_SELL) > 0 && close1 > exitHigh)
   {
      ClosePositionsByMagicAndType(
         MAGIC_BREAKOUT,
         POSITION_TYPE_SELL,
         BREAKOUT_DEVIATION_POINTS,
         "Breakout"
      );
   }

   // 2. Entry only when flat
   if(CountPositionsByMagic(MAGIC_BREAKOUT) > 0)
      return;

   double normLot = NormalizeLots(lots);
   if(normLot <= 0.0)
      return;

   if(BREAKOUT_ENABLE_BUY && close1 > entryHigh)
   {
      OpenBuyByMagic(
         MAGIC_BREAKOUT,
         normLot,
         BREAKOUT_DEVIATION_POINTS,
         "Breakout_Buy"
      );
   }
   else if(BREAKOUT_ENABLE_SELL && close1 < entryLow)
   {
      OpenSellByMagic(
         MAGIC_BREAKOUT,
         normLot,
         BREAKOUT_DEVIATION_POINTS,
         "Breakout_Sell"
      );
   }
}


//====================================================================//
// MODEL: ema_4h_5_20 (FIXED: H4 / EMA 5 vs 20 Close / Two-Way Long & Short)
// Magic: 20261140 | Prefix: EMA4H
//====================================================================//

#define EMA4H_TF                   PERIOD_H4
#define EMA4H_FAST_PERIOD          5
#define EMA4H_SLOW_PERIOD          20
#define EMA4H_DEVIATION_POINTS     30
#define MAGIC_EMA4H                20261140

ENUM_MA_METHOD     g_maMethod_EMA4H       = MODE_EMA;
ENUM_APPLIED_PRICE g_maAppliedPrice_EMA4H = PRICE_CLOSE;
datetime           g_lastBar_EMA4H        = 0;
int                g_fastHandle_EMA4H     = INVALID_HANDLE;
int                g_slowHandle_EMA4H     = INVALID_HANDLE;

bool EMA4H_GetClosedValues(double &emaFast, double &emaSlow)
{
   if(g_fastHandle_EMA4H == INVALID_HANDLE ||
      g_slowHandle_EMA4H == INVALID_HANDLE)
      return false;

   double fastBuf[];
   double slowBuf[];

   ArraySetAsSeries(fastBuf, true);
   ArraySetAsSeries(slowBuf, true);

   // shift = 1 (latest closed H4 bar, zero lookahead)
   int fastCopied = CopyBuffer(g_fastHandle_EMA4H, 0, 1, 1, fastBuf);
   int slowCopied = CopyBuffer(g_slowHandle_EMA4H, 0, 1, 1, slowBuf);

   if(fastCopied != 1 || slowCopied != 1)
      return false;

   emaFast = fastBuf[0];
   emaSlow = slowBuf[0];

   if(emaFast == EMPTY_VALUE || emaSlow == EMPTY_VALUE ||
      emaFast <= 0.0 || emaSlow <= 0.0)
      return false;

   return true;
}

void EMA4H_OpenSide(long targetType, double lots)
{
   if(targetType == POSITION_TYPE_BUY)
      OpenBuyByMagic(MAGIC_EMA4H, lots, EMA4H_DEVIATION_POINTS, "EMA4H_5_20_Buy");
   else
      OpenSellByMagic(MAGIC_EMA4H, lots, EMA4H_DEVIATION_POINTS, "EMA4H_5_20_Sell");
}

void EMA4H_SyncTwoWay(long targetType, double targetLots)
{
   targetLots = NormalizeLots(targetLots);
   if(targetLots <= 0.0)
      return;

   long oppositeType = (targetType == POSITION_TYPE_BUY)
                       ? POSITION_TYPE_SELL
                       : POSITION_TYPE_BUY;

   // 1. Close opposite side first; abort open if close fails (avoid self-hedge)
   if(CountPositionsByMagicAndType(MAGIC_EMA4H, oppositeType) > 0)
   {
      if(!ClosePositionsByMagicAndType(
            MAGIC_EMA4H,
            oppositeType,
            EMA4H_DEVIATION_POINTS,
            "EMA4H"))
         return;
   }

   // 2. Existing position on target side?
   ulong  ticket      = 0;
   double currentLots = 0.0;
   bool   hasTarget   = FindPositionByMagicAndType(MAGIC_EMA4H, targetType, ticket, currentLots);

   if(!hasTarget)
   {
      EMA4H_OpenSide(targetType, targetLots);
      return;
   }

   // 3. Resize if user changed Lot_EMA4H
   double step = VolumeStep();
   if(MathAbs(currentLots - targetLots) >= step / 2.0)
   {
      if(!ClosePositionsByMagicAndType(
            MAGIC_EMA4H,
            targetType,
            EMA4H_DEVIATION_POINTS,
            "EMA4H"))
         return;

      EMA4H_OpenSide(targetType, targetLots);
   }
}

void Init_EMA4H()
{
   g_lastBar_EMA4H = iTime(_Symbol, EMA4H_TF, 0);

   g_fastHandle_EMA4H = iMA(_Symbol, EMA4H_TF, EMA4H_FAST_PERIOD, 0,
                            g_maMethod_EMA4H, g_maAppliedPrice_EMA4H);
   g_slowHandle_EMA4H = iMA(_Symbol, EMA4H_TF, EMA4H_SLOW_PERIOD, 0,
                            g_maMethod_EMA4H, g_maAppliedPrice_EMA4H);

   if(g_fastHandle_EMA4H == INVALID_HANDLE ||
      g_slowHandle_EMA4H == INVALID_HANDLE)
   {
      Print("EMA4H failed to create EMA handles. Error=", GetLastError());
   }
}

void LogConfig_EMA4H()
{
   Print(
      "EMA4H FIXED | TF=H4 | EMA=5/20 | Two-Way=Long&Short | Magic=",
      MAGIC_EMA4H
   );
}

void EnforceDisabled_EMA4H(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_EMA4H,
         EMA4H_DEVIATION_POINTS,
         "EMA4H"
      );
   }
}

void Process_EMA4H(bool enabled, double lots)
{
   if(!IsNewBarForTimeframe(EMA4H_TF, g_lastBar_EMA4H))
      return;

   if(!enabled)
      return;

   if(Bars(_Symbol, EMA4H_TF) < EMA4H_SLOW_PERIOD + 5)
      return;

   double emaFast = 0.0;
   double emaSlow = 0.0;

   if(!EMA4H_GetClosedValues(emaFast, emaSlow))
   {
      Print("EMA4H calculation failed or insufficient H4 data.");
      return;
   }

   if(emaFast > emaSlow)
      EMA4H_SyncTwoWay(POSITION_TYPE_BUY, lots);
   else if(emaFast < emaSlow)
      EMA4H_SyncTwoWay(POSITION_TYPE_SELL, lots);
}


//====================================================================//
// MODEL: session_a_22_06 (FIXED: Broker Server Time 22:00 - 06:00 / Buy inside, Flat outside)
// Magic: 20261161 | Prefix: SessionA
//====================================================================//

#define SESSIONA_START_HOUR        22
#define SESSIONA_END_HOUR          6
#define SESSIONA_DEVIATION_POINTS  30
#define SESSIONA_RETRY_SECONDS     15
#define MAGIC_SESSIONA             20261161

datetime g_lastRetry_SessionA = 0;

bool SessionA_IsInWindow(const int hour)
{
   if(SESSIONA_START_HOUR < SESSIONA_END_HOUR)
      return (hour >= SESSIONA_START_HOUR && hour < SESSIONA_END_HOUR);

   return (hour >= SESSIONA_START_HOUR || hour < SESSIONA_END_HOUR);
}

void Init_SessionA()
{
   g_lastRetry_SessionA = 0;
}

void LogConfig_SessionA()
{
   Print(
      "SessionA FIXED | Hours=22:00-06:00 broker time | Magic=",
      MAGIC_SESSIONA
   );
}

void EnforceDisabled_SessionA(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_SESSIONA,
         SESSIONA_DEVIATION_POINTS,
         "SessionA"
      );
   }
}

void Process_SessionA(bool enabled, double lots)
{
   if(!enabled)
      return;

   double lot = NormalizeLots(lots);
   if(lot <= 0.0)
      return;

   datetime now = TimeCurrent();
   if(g_lastRetry_SessionA > 0 && (now - g_lastRetry_SessionA) < SESSIONA_RETRY_SECONDS)
      return;

   // Market-open / rollover guard: do not even evaluate while cooling down.
   if(!IsMarketTradeAllowed())
      return;

   MqlDateTime serverTime;
   if(!TimeToStruct(now, serverTime))
      return;

   bool active   = SessionA_IsInWindow(serverTime.hour);
   int  buyCount = CountPositionsByMagicAndType(MAGIC_SESSIONA, POSITION_TYPE_BUY);

   if(active)
   {
      if(buyCount == 0)
      {
         bool ok = OpenBuyByMagic(
            MAGIC_SESSIONA,
            lot,
            SESSIONA_DEVIATION_POINTS,
            "SessionA_Buy"
         );
         g_lastRetry_SessionA = ok ? 0 : now;
      }
   }
   else
   {
      if(buyCount > 0)
      {
         bool ok = ClosePositionsByMagicAndType(
            MAGIC_SESSIONA,
            POSITION_TYPE_BUY,
            SESSIONA_DEVIATION_POINTS,
            "SessionA"
         );
         g_lastRetry_SessionA = ok ? 0 : now;
      }
   }
}


//====================================================================//
// MODEL: session_b_21_04 (FIXED: Broker Server Time 21:00 - 04:00 / Buy inside, Flat outside)
// Magic: 20261162 | Prefix: SessionB
//====================================================================//

#define SESSIONB_START_HOUR        21
#define SESSIONB_END_HOUR          4
#define SESSIONB_DEVIATION_POINTS  30
#define SESSIONB_RETRY_SECONDS     15
#define MAGIC_SESSIONB             20261162

datetime g_lastRetry_SessionB = 0;

bool SessionB_IsInWindow(const int hour)
{
   if(SESSIONB_START_HOUR < SESSIONB_END_HOUR)
      return (hour >= SESSIONB_START_HOUR && hour < SESSIONB_END_HOUR);

   return (hour >= SESSIONB_START_HOUR || hour < SESSIONB_END_HOUR);
}

void Init_SessionB()
{
   g_lastRetry_SessionB = 0;
}

void LogConfig_SessionB()
{
   Print(
      "SessionB FIXED | Hours=21:00-04:00 broker time | Magic=",
      MAGIC_SESSIONB
   );
}

void EnforceDisabled_SessionB(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_SESSIONB,
         SESSIONB_DEVIATION_POINTS,
         "SessionB"
      );
   }
}

void Process_SessionB(bool enabled, double lots)
{
   if(!enabled)
      return;

   double lot = NormalizeLots(lots);
   if(lot <= 0.0)
      return;

   datetime now = TimeCurrent();
   if(g_lastRetry_SessionB > 0 && (now - g_lastRetry_SessionB) < SESSIONB_RETRY_SECONDS)
      return;

   // Market-open / rollover guard: do not even evaluate while cooling down.
   if(!IsMarketTradeAllowed())
      return;

   MqlDateTime serverTime;
   if(!TimeToStruct(now, serverTime))
      return;

   bool active   = SessionB_IsInWindow(serverTime.hour);
   int  buyCount = CountPositionsByMagicAndType(MAGIC_SESSIONB, POSITION_TYPE_BUY);

   if(active)
   {
      if(buyCount == 0)
      {
         bool ok = OpenBuyByMagic(
            MAGIC_SESSIONB,
            lot,
            SESSIONB_DEVIATION_POINTS,
            "SessionB_Buy"
         );
         g_lastRetry_SessionB = ok ? 0 : now;
      }
   }
   else
   {
      if(buyCount > 0)
      {
         bool ok = ClosePositionsByMagicAndType(
            MAGIC_SESSIONB,
            POSITION_TYPE_BUY,
            SESSIONB_DEVIATION_POINTS,
            "SessionB"
         );
         g_lastRetry_SessionB = ok ? 0 : now;
      }
   }
}


//====================================================================//
// DISABLE CONTROL
// false or 0 lot = no new entry and close that model's positions
//====================================================================//

void EnforceDisabledModels()
{
   datetime now = TimeCurrent();
   if(g_lastDisableCheck > 0 &&
      (now - g_lastDisableCheck) < DISABLE_CHECK_INTERVAL_SECONDS)
      return;

   g_lastDisableCheck = now;

   EnforceDisabled_Alpha005(Enable_Alpha005, Lot_Alpha005);
   EnforceDisabled_Alpha055(Enable_Alpha055, Lot_Alpha055);
   EnforceDisabled_Alpha010(Enable_Alpha010, Lot_Alpha010);
   EnforceDisabled_Heiken(Enable_Heiken, Lot_Heiken);
   EnforceDisabled_MACross(Enable_MACross, Lot_MACross);
   EnforceDisabled_Breakout(Enable_Breakout, Lot_Breakout);
   EnforceDisabled_EMA4H(Enable_EMA4H, Lot_EMA4H);
   EnforceDisabled_SessionA(Enable_SessionA, Lot_SessionA);
   EnforceDisabled_SessionB(Enable_SessionB, Lot_SessionB);
}


//====================================================================//
// INIT
//====================================================================//

int OnInit()
{
   long login = (long)AccountInfoInteger(ACCOUNT_LOGIN);

   if(Account_Lock > 0 && login != Account_Lock)
   {
      Print("ACCOUNT LOCK FAILED | Allowed=", Account_Lock, " | Current=", login);
      return INIT_FAILED;
   }

   if(!IsHedgingAccount())
   {
      Print("ERROR: This EA requires an MT5 HEDGING account.");
      return INIT_FAILED;
   }

   if(Lot_Alpha005 < 0.0 ||
      Lot_Alpha055 < 0.0 ||
      Lot_Alpha010 < 0.0 ||
      Lot_Heiken < 0.0 ||
      Lot_MACross < 0.0 ||
      Lot_Breakout < 0.0 ||
      Lot_EMA4H < 0.0 ||
      Lot_SessionA < 0.0 ||
      Lot_SessionB < 0.0)
   {
      Print("ERROR: Lot values must be >= 0.");
      return INIT_PARAMETERS_INCORRECT;
   }

   trade.SetTypeFillingBySymbol(_Symbol);

   Init_Alpha005();
   Init_Alpha055();
   Init_Alpha010();
   Init_Heiken();
   Init_MACross();
   Init_Breakout();
   Init_EMA4H();
   Init_SessionA();
   Init_SessionB();

   Print(
      "AlphaMining_PortfolioC_9Models_v2 initialized | Account=", login,
      " | Alpha005=", Enable_Alpha005,
      " | Alpha055=", Enable_Alpha055,
      " | Alpha010=", Enable_Alpha010,
      " | Heiken=", Enable_Heiken,
      " | MACross=", Enable_MACross,
      " | Breakout=", Enable_Breakout,
      " | EMA4H=", Enable_EMA4H,
      " | SessionA=", Enable_SessionA,
      " | SessionB=", Enable_SessionB
   );

   LogConfig_Alpha005();
   LogConfig_Alpha055();
   LogConfig_Alpha010();
   LogConfig_Heiken();
   LogConfig_MACross();
   LogConfig_Breakout();
   LogConfig_EMA4H();
   LogConfig_SessionA();
   LogConfig_SessionB();

   return INIT_SUCCEEDED;
}


//====================================================================//
// MAIN
//====================================================================//

void OnTick()
{
   EnforceDisabledModels();

   // Independent per-model execution & bar clocks
   Process_Alpha005(Enable_Alpha005, Lot_Alpha005);
   Process_Alpha055(Enable_Alpha055, Lot_Alpha055);
   Process_Alpha010(Enable_Alpha010, Lot_Alpha010);
   Process_Heiken(Enable_Heiken, Lot_Heiken);
   Process_MACross(Enable_MACross, Lot_MACross);
   Process_Breakout(Enable_Breakout, Lot_Breakout);
   Process_EMA4H(Enable_EMA4H, Lot_EMA4H);
   Process_SessionA(Enable_SessionA, Lot_SessionA);
   Process_SessionB(Enable_SessionB, Lot_SessionB);
}
//+------------------------------------------------------------------+
