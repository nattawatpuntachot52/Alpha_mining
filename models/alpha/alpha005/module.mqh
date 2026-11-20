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
