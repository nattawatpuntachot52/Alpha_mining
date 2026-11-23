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
