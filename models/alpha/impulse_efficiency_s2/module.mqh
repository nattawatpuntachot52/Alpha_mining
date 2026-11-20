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
