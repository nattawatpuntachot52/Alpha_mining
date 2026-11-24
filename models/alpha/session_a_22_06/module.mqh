//====================================================================//
// MODEL: session_a_22_06 (FIXED: Broker Server Time 22:00 - 06:00 / Buy inside, Flat outside)
// Magic: 20261161 | Prefix: SessionA
//====================================================================//

#define SESSIONA_START_HOUR        22
#define SESSIONA_END_HOUR          6
#define SESSIONA_DEVIATION_POINTS  30
#define SESSIONA_RETRY_SECONDS     15
#define MAGIC_SESSIONA             20261161

datetime g_lastRetry_SessionA = 0;

bool SessionA_IsInWindow(const int hour)
{
   if(SESSIONA_START_HOUR < SESSIONA_END_HOUR)
      return (hour >= SESSIONA_START_HOUR && hour < SESSIONA_END_HOUR);

   return (hour >= SESSIONA_START_HOUR || hour < SESSIONA_END_HOUR);
}

void Init_SessionA()
{
   g_lastRetry_SessionA = 0;
}

void LogConfig_SessionA()
{
   Print(
      "SessionA FIXED | Hours=22:00-06:00 broker time | Magic=",
      MAGIC_SESSIONA
   );
}

void EnforceDisabled_SessionA(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_SESSIONA,
         SESSIONA_DEVIATION_POINTS,
         "SessionA"
      );
   }
}

void Process_SessionA(bool enabled, double lots)
{
   if(!enabled)
      return;

   double lot = NormalizeLots(lots);
   if(lot <= 0.0)
      return;

   datetime now = TimeCurrent();
   if(g_lastRetry_SessionA > 0 && (now - g_lastRetry_SessionA) < SESSIONA_RETRY_SECONDS)
      return;

   // Market-open / rollover guard: do not even evaluate while cooling down.
   if(!IsMarketTradeAllowed())
      return;

   MqlDateTime serverTime;
   if(!TimeToStruct(now, serverTime))
      return;

   bool active   = SessionA_IsInWindow(serverTime.hour);
   int  buyCount = CountPositionsByMagicAndType(MAGIC_SESSIONA, POSITION_TYPE_BUY);

   if(active)
   {
      if(buyCount == 0)
      {
         bool ok = OpenBuyByMagic(
            MAGIC_SESSIONA,
            lot,
            SESSIONA_DEVIATION_POINTS,
            "SessionA_Buy"
         );
         g_lastRetry_SessionA = ok ? 0 : now;
      }
   }
   else
   {
      if(buyCount > 0)
      {
         bool ok = ClosePositionsByMagicAndType(
            MAGIC_SESSIONA,
            POSITION_TYPE_BUY,
            SESSIONA_DEVIATION_POINTS,
            "SessionA"
         );
         g_lastRetry_SessionA = ok ? 0 : now;
      }
   }
}
