//====================================================================//
// MODEL: session_b_21_04 (FIXED: Broker Server Time 21:00 - 04:00 / Buy inside, Flat outside)
// Magic: 20261162 | Prefix: SessionB
//====================================================================//

#define SESSIONB_START_HOUR        21
#define SESSIONB_END_HOUR          4
#define SESSIONB_DEVIATION_POINTS  30
#define SESSIONB_RETRY_SECONDS     15
#define MAGIC_SESSIONB             20261162

datetime g_lastRetry_SessionB = 0;

bool SessionB_IsInWindow(const int hour)
{
   if(SESSIONB_START_HOUR < SESSIONB_END_HOUR)
      return (hour >= SESSIONB_START_HOUR && hour < SESSIONB_END_HOUR);

   return (hour >= SESSIONB_START_HOUR || hour < SESSIONB_END_HOUR);
}

void Init_SessionB()
{
   g_lastRetry_SessionB = 0;
}

void LogConfig_SessionB()
{
   Print(
      "SessionB FIXED | Hours=21:00-04:00 broker time | Magic=",
      MAGIC_SESSIONB
   );
}

void EnforceDisabled_SessionB(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_SESSIONB,
         SESSIONB_DEVIATION_POINTS,
         "SessionB"
      );
   }
}

void Process_SessionB(bool enabled, double lots)
{
   if(!enabled)
      return;

   double lot = NormalizeLots(lots);
   if(lot <= 0.0)
      return;

   datetime now = TimeCurrent();
   if(g_lastRetry_SessionB > 0 && (now - g_lastRetry_SessionB) < SESSIONB_RETRY_SECONDS)
      return;

   // Market-open / rollover guard: do not even evaluate while cooling down.
   if(!IsMarketTradeAllowed())
      return;

   MqlDateTime serverTime;
   if(!TimeToStruct(now, serverTime))
      return;

   bool active   = SessionB_IsInWindow(serverTime.hour);
   int  buyCount = CountPositionsByMagicAndType(MAGIC_SESSIONB, POSITION_TYPE_BUY);

   if(active)
   {
      if(buyCount == 0)
      {
         bool ok = OpenBuyByMagic(
            MAGIC_SESSIONB,
            lot,
            SESSIONB_DEVIATION_POINTS,
            "SessionB_Buy"
         );
         g_lastRetry_SessionB = ok ? 0 : now;
      }
   }
   else
   {
      if(buyCount > 0)
      {
         bool ok = ClosePositionsByMagicAndType(
            MAGIC_SESSIONB,
            POSITION_TYPE_BUY,
            SESSIONB_DEVIATION_POINTS,
            "SessionB"
         );
         g_lastRetry_SessionB = ok ? 0 : now;
      }
   }
}
