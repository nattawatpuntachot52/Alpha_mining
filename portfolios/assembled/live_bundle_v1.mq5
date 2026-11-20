//+------------------------------------------------------------------+
//| AlphaMining_LiveBundle_v1.mq5
//| AUTO-GENERATED DETERMINISTICALLY BY scripts/build_ea_portfolio.py
//| Portfolio ID : live_bundle_v1
//| Core Helpers : sha=919b5f1ac453
//| Account Mode : MT5 Hedging required
//|
//| Included Models (editable inputs: Enable & Lot only):
//|  1) Alpha005   [alpha] v1.0.0 | magic=5105005 | status=exploratory | sha=7567ea26062c
//|  2) Alpha055   [alpha] v1.0.0 | magic=5105055 | status=exploratory | sha=ce1fa714ae96
//|  3) Alpha010   [alpha] v1.0.0 | magic=5105010 | status=exploratory | sha=b88f009d8808
//|  4) Heiken     [alpha] v1.0.0 | magic=20260616 | status=exploratory | sha=6731b05c5959
//|  5) Impulse1   [alpha] v1.0.0 | magic=20261101 | status=exploratory | sha=f334b3f90130
//|  6) Impulse2   [alpha] v1.0.0 | magic=20261102 | status=exploratory | sha=6a26036ece5a
//|  7) Day20      [alpha] v1.0.0 | magic=20261120 | status=proposed | sha=385f184911af
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

// impulse_efficiency_s1 — Impulse Efficiency S1 (H1 Z_t/ER_t | SL 0.75% / TP 0.50%)
input bool   Enable_Impulse1 = true;
input double Lot_Impulse1    = 0.01;

// impulse_efficiency_s2 — Impulse Efficiency S2 (H1 Z_t/ER_t | SL 0.50% / TP 3.00%)
input bool   Enable_Impulse2 = true;
input double Lot_Impulse2    = 0.01;

// monthly_day20 — Monthly Day-20 Calendar Long (Open Day 20 -> After Close Day 21)
input bool   Enable_Day20 = true;
input double Lot_Day20    = 0.01;


//====================================================================//
// SHARED CORE EXECUTION & POSITION HELPERS (MT5 Hedging Account)
// Source: models/mql5_core/execution_helpers.mqh
//====================================================================//

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

bool FindBuyPositionByMagic(long magic,
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

      if((long)PositionGetInteger(POSITION_TYPE) != POSITION_TYPE_BUY)
         continue;

      ticket = currentTicket;
      volume = PositionGetDouble(POSITION_VOLUME);
      return true;
   }

   return false;
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

bool OpenBuyByMagic(long magic,
                    double lots,
                    int deviationPoints,
                    string label)
{
   lots = NormalizeLots(lots);

   if(lots <= 0.0)
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

   trade.SetExpertMagicNumber(magic);
   trade.SetDeviationInPoints(deviationPoints);

   bool ok = trade.PositionClose(ticket);

   if(!ok)
   {
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

void CloseAllPositionsByMagic(long magic,
                              int deviationPoints,
                              string label)
{
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
// MODEL: impulse_efficiency_s1 (H1 Z_t + ER_t | SL 0.75% / TP 0.50%)
// Magic: 20261101 | Prefix: Impulse1
//====================================================================//

#define IMPULSE1_TF                PERIOD_H1
#define IMPULSE1_ENABLE_BUY        true
#define IMPULSE1_ENABLE_SELL       true
#define IMPULSE1_MOVE_K            3
#define IMPULSE1_VOL_W             20
#define IMPULSE1_Z_THRESHOLD       2.0
#define IMPULSE1_ER_THRESHOLD      0.75
#define IMPULSE1_SL_PCT            0.75
#define IMPULSE1_TP_PCT            0.50
#define IMPULSE1_MAX_SPREAD_POINTS 50
#define IMPULSE1_DEVIATION_POINTS  20
#define MAGIC_IMPULSE1             20261101

datetime g_lastBar_Impulse1 = 0;

bool Impulse1_ComputeMetrics(double &out_z, double &out_er)
{
   int totalNeeded = IMPULSE1_MOVE_K + IMPULSE1_VOL_W + 1;
   double closeBuf[];
   ArraySetAsSeries(closeBuf, true);

   // Closed bars only (shift = 1) to prevent intrabar lookahead.
   int copied = CopyClose(_Symbol, IMPULSE1_TF, 1, totalNeeded, closeBuf);
   if(copied < totalNeeded)
      return false;

   double sumSqDiff = 0.0;
   for(int j = IMPULSE1_MOVE_K; j < IMPULSE1_MOVE_K + IMPULSE1_VOL_W; j++)
   {
      double diff = closeBuf[j] - closeBuf[j + 1];
      sumSqDiff += diff * diff;
   }

   double sigmaBase = MathSqrt(sumSqDiff / (double)IMPULSE1_VOL_W);
   double point     = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   if(sigmaBase < point)
      sigmaBase = point;

   double netMove   = closeBuf[0] - closeBuf[IMPULSE1_MOVE_K];
   double totalPath = 0.0;
   for(int i = 0; i < IMPULSE1_MOVE_K; i++)
   {
      totalPath += MathAbs(closeBuf[i] - closeBuf[i + 1]);
   }

   if(totalPath <= 0.0)
      return false;

   out_z  = netMove / (sigmaBase * MathSqrt((double)IMPULSE1_MOVE_K));
   out_er = MathAbs(netMove) / totalPath;
   return true;
}

void Init_Impulse1()
{
   g_lastBar_Impulse1 = iTime(_Symbol, IMPULSE1_TF, 0);
}

void LogConfig_Impulse1()
{
   Print(
      "Impulse1 FIXED | TF=H1 | k=3 | W=20 | Z=2.0 | ER=0.75 | SL=0.75% | TP=0.50% | Magic=",
      MAGIC_IMPULSE1
   );
}

void EnforceDisabled_Impulse1(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_IMPULSE1,
         IMPULSE1_DEVIATION_POINTS,
         "Impulse1"
      );
   }
}

void Process_Impulse1(bool enabled, double lots)
{
   if(!IsNewBarForTimeframe(IMPULSE1_TF, g_lastBar_Impulse1))
      return;

   if(!enabled || NormalizeLots(lots) <= 0.0)
      return;

   if(CountPositionsByMagic(MAGIC_IMPULSE1) > 0)
      return;

   double zVal  = 0.0;
   double erVal = 0.0;
   if(!Impulse1_ComputeMetrics(zVal, erVal))
      return;

   string comment = StringFormat("Imp1|Z=%.2f|ER=%.2f", zVal, erVal);

   if(IMPULSE1_ENABLE_BUY && zVal >= IMPULSE1_Z_THRESHOLD && erVal >= IMPULSE1_ER_THRESHOLD)
   {
      OpenPctSlTpOrderByMagic(
         MAGIC_IMPULSE1,
         lots,
         ORDER_TYPE_BUY,
         IMPULSE1_SL_PCT,
         IMPULSE1_TP_PCT,
         IMPULSE1_MAX_SPREAD_POINTS,
         IMPULSE1_DEVIATION_POINTS,
         comment,
         "Impulse1"
      );
   }
   else if(IMPULSE1_ENABLE_SELL && zVal <= -IMPULSE1_Z_THRESHOLD && erVal >= IMPULSE1_ER_THRESHOLD)
   {
      OpenPctSlTpOrderByMagic(
         MAGIC_IMPULSE1,
         lots,
         ORDER_TYPE_SELL,
         IMPULSE1_SL_PCT,
         IMPULSE1_TP_PCT,
         IMPULSE1_MAX_SPREAD_POINTS,
         IMPULSE1_DEVIATION_POINTS,
         comment,
         "Impulse1"
      );
   }
}


//====================================================================//
// MODEL: impulse_efficiency_s2 (H1 Z_t + ER_t | SL 0.50% / TP 3.00%)
// Magic: 20261102 | Prefix: Impulse2
//====================================================================//

#define IMPULSE2_TF                PERIOD_H1
#define IMPULSE2_ENABLE_BUY        true
#define IMPULSE2_ENABLE_SELL       true
#define IMPULSE2_MOVE_K            3
#define IMPULSE2_VOL_W             20
#define IMPULSE2_Z_THRESHOLD       2.0
#define IMPULSE2_ER_THRESHOLD      0.75
#define IMPULSE2_SL_PCT            0.50
#define IMPULSE2_TP_PCT            3.00
#define IMPULSE2_MAX_SPREAD_POINTS 50
#define IMPULSE2_DEVIATION_POINTS  20
#define MAGIC_IMPULSE2             20261102

datetime g_lastBar_Impulse2 = 0;

bool Impulse2_ComputeMetrics(double &out_z, double &out_er)
{
   int totalNeeded = IMPULSE2_MOVE_K + IMPULSE2_VOL_W + 1;
   double closeBuf[];
   ArraySetAsSeries(closeBuf, true);

   // Closed bars only (shift = 1) to prevent intrabar lookahead.
   int copied = CopyClose(_Symbol, IMPULSE2_TF, 1, totalNeeded, closeBuf);
   if(copied < totalNeeded)
      return false;

   double sumSqDiff = 0.0;
   for(int j = IMPULSE2_MOVE_K; j < IMPULSE2_MOVE_K + IMPULSE2_VOL_W; j++)
   {
      double diff = closeBuf[j] - closeBuf[j + 1];
      sumSqDiff += diff * diff;
   }

   double sigmaBase = MathSqrt(sumSqDiff / (double)IMPULSE2_VOL_W);
   double point     = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   if(sigmaBase < point)
      sigmaBase = point;

   double netMove   = closeBuf[0] - closeBuf[IMPULSE2_MOVE_K];
   double totalPath = 0.0;
   for(int i = 0; i < IMPULSE2_MOVE_K; i++)
   {
      totalPath += MathAbs(closeBuf[i] - closeBuf[i + 1]);
   }

   if(totalPath <= 0.0)
      return false;

   out_z  = netMove / (sigmaBase * MathSqrt((double)IMPULSE2_MOVE_K));
   out_er = MathAbs(netMove) / totalPath;
   return true;
}

void Init_Impulse2()
{
   g_lastBar_Impulse2 = iTime(_Symbol, IMPULSE2_TF, 0);
}

void LogConfig_Impulse2()
{
   Print(
      "Impulse2 FIXED | TF=H1 | k=3 | W=20 | Z=2.0 | ER=0.75 | SL=0.50% | TP=3.00% | Magic=",
      MAGIC_IMPULSE2
   );
}

void EnforceDisabled_Impulse2(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_IMPULSE2,
         IMPULSE2_DEVIATION_POINTS,
         "Impulse2"
      );
   }
}

void Process_Impulse2(bool enabled, double lots)
{
   if(!IsNewBarForTimeframe(IMPULSE2_TF, g_lastBar_Impulse2))
      return;

   if(!enabled || NormalizeLots(lots) <= 0.0)
      return;

   if(CountPositionsByMagic(MAGIC_IMPULSE2) > 0)
      return;

   double zVal  = 0.0;
   double erVal = 0.0;
   if(!Impulse2_ComputeMetrics(zVal, erVal))
      return;

   string comment = StringFormat("Imp2|Z=%.2f|ER=%.2f", zVal, erVal);

   if(IMPULSE2_ENABLE_BUY && zVal >= IMPULSE2_Z_THRESHOLD && erVal >= IMPULSE2_ER_THRESHOLD)
   {
      OpenPctSlTpOrderByMagic(
         MAGIC_IMPULSE2,
         lots,
         ORDER_TYPE_BUY,
         IMPULSE2_SL_PCT,
         IMPULSE2_TP_PCT,
         IMPULSE2_MAX_SPREAD_POINTS,
         IMPULSE2_DEVIATION_POINTS,
         comment,
         "Impulse2"
      );
   }
   else if(IMPULSE2_ENABLE_SELL && zVal <= -IMPULSE2_Z_THRESHOLD && erVal >= IMPULSE2_ER_THRESHOLD)
   {
      OpenPctSlTpOrderByMagic(
         MAGIC_IMPULSE2,
         lots,
         ORDER_TYPE_SELL,
         IMPULSE2_SL_PCT,
         IMPULSE2_TP_PCT,
         IMPULSE2_MAX_SPREAD_POINTS,
         IMPULSE2_DEVIATION_POINTS,
         comment,
         "Impulse2"
      );
   }
}


//====================================================================//
// MODEL: monthly_day20 (Buy Day 20 D1 Open -> Close After Day 21 End)
// Magic: 20261120 | Prefix: Day20
//====================================================================//

#define DAY20_TF               PERIOD_D1
#define DAY20_ENTRY_DAY        20
#define DAY20_EXIT_DAY         22
#define DAY20_DEVIATION_POINTS 20
#define DAY20_RETRY_SECONDS    15
#define MAGIC_DAY20            20261120

datetime g_lastBar_Day20        = 0;
int      g_pendingEntryYM_Day20 = 0;
int      g_openedYM_Day20       = 0;
datetime g_lastEntryRetry_Day20 = 0;
datetime g_lastExitRetry_Day20  = 0;

void Day20_CheckAndClosePositions(const MqlDateTime &curDt, int curYM)
{
   datetime now = TimeCurrent();
   if(g_lastExitRetry_Day20 > 0 && (now - g_lastExitRetry_Day20) < DAY20_RETRY_SECONDS)
      return;

   bool anyFailed = false;
   trade.SetExpertMagicNumber(MAGIC_DAY20);
   trade.SetDeviationInPoints(DAY20_DEVIATION_POINTS);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(!PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;

      if((long)PositionGetInteger(POSITION_MAGIC) != MAGIC_DAY20)
         continue;

      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
      MqlDateTime openDt;
      TimeToStruct(openTime, openDt);
      int openYM = openDt.year * 100 + openDt.mon;

      bool shouldClose = (curYM > openYM) || (curDt.day >= DAY20_EXIT_DAY);
      if(!shouldClose)
         continue;

      bool ok = trade.PositionClose(ticket);
      if(!ok)
      {
         anyFailed = true;
         Print(
            "Day20 CLOSE failed | ticket=",
            ticket,
            " | retcode=",
            trade.ResultRetcode(),
            " | ",
            trade.ResultRetcodeDescription()
         );
      }
   }

   g_lastExitRetry_Day20 = anyFailed ? now : 0;
}

void Init_Day20()
{
   g_lastBar_Day20        = iTime(_Symbol, DAY20_TF, 0);
   g_pendingEntryYM_Day20 = 0;
   g_openedYM_Day20       = 0;
   g_lastEntryRetry_Day20 = 0;
   g_lastExitRetry_Day20  = 0;
}

void LogConfig_Day20()
{
   Print(
      "Day20 FIXED | TF=D1 | Entry=Day 20 Open | Exit=After Day 21 Close (Day >= 22 Open) | Magic=",
      MAGIC_DAY20
   );
}

void EnforceDisabled_Day20(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_DAY20,
         DAY20_DEVIATION_POINTS,
         "Day20"
      );
   }
}

void Process_Day20(bool enabled, double lots)
{
   datetime curDayBar = iTime(_Symbol, DAY20_TF, 0);
   if(curDayBar <= 0)
      return;

   MqlDateTime curDt;
   TimeToStruct(curDayBar, curDt);
   int curYM = curDt.year * 100 + curDt.mon;

   if(curDayBar != g_lastBar_Day20)
   {
      g_lastBar_Day20 = curDayBar;

      if(curDt.day == DAY20_ENTRY_DAY && curYM != g_openedYM_Day20)
      {
         g_pendingEntryYM_Day20 = curYM;
         g_lastEntryRetry_Day20 = 0;
      }
      else if(curDt.day != DAY20_ENTRY_DAY)
      {
         g_pendingEntryYM_Day20 = 0;
         g_lastEntryRetry_Day20 = 0;
      }
   }

   if(CountPositionsByMagic(MAGIC_DAY20) > 0)
   {
      Day20_CheckAndClosePositions(curDt, curYM);
   }

   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      g_pendingEntryYM_Day20 = 0;
      return;
   }

   if(g_pendingEntryYM_Day20 != curYM || curDt.day != DAY20_ENTRY_DAY)
      return;

   if(CountPositionsByMagic(MAGIC_DAY20) > 0)
   {
      g_openedYM_Day20       = curYM;
      g_pendingEntryYM_Day20 = 0;
      g_lastEntryRetry_Day20 = 0;
      return;
   }

   datetime now = TimeCurrent();
   if(g_lastEntryRetry_Day20 > 0 && (now - g_lastEntryRetry_Day20) < DAY20_RETRY_SECONDS)
      return;

   bool ok = OpenBuyByMagic(
      MAGIC_DAY20,
      lots,
      DAY20_DEVIATION_POINTS,
      "Day20_Buy"
   );

   if(ok)
   {
      g_openedYM_Day20       = curYM;
      g_pendingEntryYM_Day20 = 0;
      g_lastEntryRetry_Day20 = 0;
   }
   else
   {
      g_lastEntryRetry_Day20 = now;
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
   EnforceDisabled_Impulse1(Enable_Impulse1, Lot_Impulse1);
   EnforceDisabled_Impulse2(Enable_Impulse2, Lot_Impulse2);
   EnforceDisabled_Day20(Enable_Day20, Lot_Day20);
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
      Lot_Impulse1 < 0.0 ||
      Lot_Impulse2 < 0.0 ||
      Lot_Day20 < 0.0)
   {
      Print("ERROR: Lot values must be >= 0.");
      return INIT_PARAMETERS_INCORRECT;
   }

   trade.SetTypeFillingBySymbol(_Symbol);

   Init_Alpha005();
   Init_Alpha055();
   Init_Alpha010();
   Init_Heiken();
   Init_Impulse1();
   Init_Impulse2();
   Init_Day20();

   Print(
      "AlphaMining_LiveBundle_v1 initialized | Account=", login,
      " | Alpha005=", Enable_Alpha005,
      " | Alpha055=", Enable_Alpha055,
      " | Alpha010=", Enable_Alpha010,
      " | Heiken=", Enable_Heiken,
      " | Impulse1=", Enable_Impulse1,
      " | Impulse2=", Enable_Impulse2,
      " | Day20=", Enable_Day20
   );

   LogConfig_Alpha005();
   LogConfig_Alpha055();
   LogConfig_Alpha010();
   LogConfig_Heiken();
   LogConfig_Impulse1();
   LogConfig_Impulse2();
   LogConfig_Day20();

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
   Process_Impulse1(Enable_Impulse1, Lot_Impulse1);
   Process_Impulse2(Enable_Impulse2, Lot_Impulse2);
   Process_Day20(Enable_Day20, Lot_Day20);
}
//+------------------------------------------------------------------+
