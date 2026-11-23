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
