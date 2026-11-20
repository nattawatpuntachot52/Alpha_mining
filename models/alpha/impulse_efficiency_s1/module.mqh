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
