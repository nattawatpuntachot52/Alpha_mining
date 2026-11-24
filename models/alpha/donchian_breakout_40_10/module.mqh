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
