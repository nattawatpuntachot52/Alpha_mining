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
