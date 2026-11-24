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
