//====================================================================//
// MODEL: monthly_day20 (Buy Day 20 D1 Open -> Close After Day 21 End)
// Magic: 20261120 | Prefix: Day20
//====================================================================//

#define DAY20_TF               PERIOD_D1
#define DAY20_ENTRY_DAY        20
#define DAY20_EXIT_DAY         22
#define DAY20_DEVIATION_POINTS 20
#define DAY20_RETRY_SECONDS    15
#define MAGIC_DAY20            20261120

datetime g_lastBar_Day20        = 0;
int      g_pendingEntryYM_Day20 = 0;
int      g_openedYM_Day20       = 0;
datetime g_lastEntryRetry_Day20 = 0;
datetime g_lastExitRetry_Day20  = 0;

void Day20_CheckAndClosePositions(const MqlDateTime &curDt, int curYM)
{
   datetime now = TimeCurrent();
   if(g_lastExitRetry_Day20 > 0 && (now - g_lastExitRetry_Day20) < DAY20_RETRY_SECONDS)
      return;

   bool anyFailed = false;
   trade.SetExpertMagicNumber(MAGIC_DAY20);
   trade.SetDeviationInPoints(DAY20_DEVIATION_POINTS);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(!PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;

      if((long)PositionGetInteger(POSITION_MAGIC) != MAGIC_DAY20)
         continue;

      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
      MqlDateTime openDt;
      TimeToStruct(openTime, openDt);
      int openYM = openDt.year * 100 + openDt.mon;

      bool shouldClose = (curYM > openYM) || (curDt.day >= DAY20_EXIT_DAY);
      if(!shouldClose)
         continue;

      bool ok = trade.PositionClose(ticket);
      if(!ok)
      {
         anyFailed = true;
         Print(
            "Day20 CLOSE failed | ticket=",
            ticket,
            " | retcode=",
            trade.ResultRetcode(),
            " | ",
            trade.ResultRetcodeDescription()
         );
      }
   }

   g_lastExitRetry_Day20 = anyFailed ? now : 0;
}

void Init_Day20()
{
   g_lastBar_Day20        = iTime(_Symbol, DAY20_TF, 0);
   g_pendingEntryYM_Day20 = 0;
   g_openedYM_Day20       = 0;
   g_lastEntryRetry_Day20 = 0;
   g_lastExitRetry_Day20  = 0;
}

void LogConfig_Day20()
{
   Print(
      "Day20 FIXED | TF=D1 | Entry=Day 20 Open | Exit=After Day 21 Close (Day >= 22 Open) | Magic=",
      MAGIC_DAY20
   );
}

void EnforceDisabled_Day20(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_DAY20,
         DAY20_DEVIATION_POINTS,
         "Day20"
      );
   }
}

void Process_Day20(bool enabled, double lots)
{
   datetime curDayBar = iTime(_Symbol, DAY20_TF, 0);
   if(curDayBar <= 0)
      return;

   MqlDateTime curDt;
   TimeToStruct(curDayBar, curDt);
   int curYM = curDt.year * 100 + curDt.mon;

   if(curDayBar != g_lastBar_Day20)
   {
      g_lastBar_Day20 = curDayBar;

      if(curDt.day == DAY20_ENTRY_DAY && curYM != g_openedYM_Day20)
      {
         g_pendingEntryYM_Day20 = curYM;
         g_lastEntryRetry_Day20 = 0;
      }
      else if(curDt.day != DAY20_ENTRY_DAY)
      {
         g_pendingEntryYM_Day20 = 0;
         g_lastEntryRetry_Day20 = 0;
      }
   }

   if(CountPositionsByMagic(MAGIC_DAY20) > 0)
   {
      Day20_CheckAndClosePositions(curDt, curYM);
   }

   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      g_pendingEntryYM_Day20 = 0;
      return;
   }

   if(g_pendingEntryYM_Day20 != curYM || curDt.day != DAY20_ENTRY_DAY)
      return;

   if(CountPositionsByMagic(MAGIC_DAY20) > 0)
   {
      g_openedYM_Day20       = curYM;
      g_pendingEntryYM_Day20 = 0;
      g_lastEntryRetry_Day20 = 0;
      return;
   }

   datetime now = TimeCurrent();
   if(g_lastEntryRetry_Day20 > 0 && (now - g_lastEntryRetry_Day20) < DAY20_RETRY_SECONDS)
      return;

   bool ok = OpenBuyByMagic(
      MAGIC_DAY20,
      lots,
      DAY20_DEVIATION_POINTS,
      "Day20_Buy"
   );

   if(ok)
   {
      g_openedYM_Day20       = curYM;
      g_pendingEntryYM_Day20 = 0;
      g_lastEntryRetry_Day20 = 0;
   }
   else
   {
      g_lastEntryRetry_Day20 = now;
   }
}
