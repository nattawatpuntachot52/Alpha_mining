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
