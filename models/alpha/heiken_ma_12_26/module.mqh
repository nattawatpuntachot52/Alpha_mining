//====================================================================//
// MODEL: heiken_ma_12_26 (FIXED: M15 / HA Close / SMA 12-26)
// Magic: 20260616 | Prefix: Heiken
//====================================================================//

#define HEIKEN_TF                PERIOD_M15
#define HEIKEN_MAX_SPREAD_POINTS 1000
#define HEIKEN_FAST_MA           12
#define HEIKEN_SLOW_MA           26
#define HEIKEN_DEVIATION_POINTS  30
#define HEIKEN_STOP_THURSDAY     true
#define HEIKEN_STOP_SUNDAY       false
#define MAGIC_HEIKEN             20260616

ENUM_MA_METHOD     g_haMAMethod_Heiken     = MODE_SMA;
ENUM_APPLIED_PRICE g_haAppliedPrice_Heiken = PRICE_CLOSE;
datetime           g_lastBar_Heiken        = 0;

bool Heiken_SpreadOK()
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(ask <= 0.0 || bid <= 0.0)
      return false;

   double spreadPoints = (ask - bid) / _Point;

   return (
      spreadPoints <= HEIKEN_MAX_SPREAD_POINTS
   );
}

bool Heiken_TradingDayAllowed()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);

   if(HEIKEN_STOP_SUNDAY && dt.day_of_week == 0)
      return false;

   if(HEIKEN_STOP_THURSDAY && dt.day_of_week == 4)
      return false;

   return true;
}

double Heiken_GetAppliedPrice(double haOpen,
                              double haHigh,
                              double haLow,
                              double haClose)
{
   switch(g_haAppliedPrice_Heiken)
   {
      case PRICE_OPEN:
         return haOpen;

      case PRICE_HIGH:
         return haHigh;

      case PRICE_LOW:
         return haLow;

      case PRICE_MEDIAN:
         return (haHigh + haLow) / 2.0;

      case PRICE_TYPICAL:
         return (haHigh + haLow + haClose) / 3.0;

      case PRICE_WEIGHTED:
         return (haHigh + haLow + 2.0 * haClose) / 4.0;

      case PRICE_CLOSE:
      default:
         return haClose;
   }
}

bool Heiken_BuildSeries(double &haOpenArr[],
                        double &haHighArr[],
                        double &haLowArr[],
                        double &haCloseArr[],
                        double &haPriceArr[],
                        int &closedIndex,
                        int minimumBarsRequired)
{
   int barsAvailable = Bars(_Symbol, HEIKEN_TF);

   if(barsAvailable < minimumBarsRequired)
      return false;

   int requestedBars =
      minimumBarsRequired * 10 + 100;

   if(requestedBars < 1000)
      requestedBars = 1000;

   if(requestedBars > barsAvailable)
      requestedBars = barsAvailable;

   MqlRates rates[];
   ArraySetAsSeries(rates, false);

   int copied = CopyRates(
      _Symbol,
      HEIKEN_TF,
      0,
      requestedBars,
      rates
   );

   if(copied < minimumBarsRequired)
      return false;

   ArrayResize(haOpenArr,  copied);
   ArrayResize(haHighArr,  copied);
   ArrayResize(haLowArr,   copied);
   ArrayResize(haCloseArr, copied);
   ArrayResize(haPriceArr, copied);

   ArraySetAsSeries(haOpenArr,  false);
   ArraySetAsSeries(haHighArr,  false);
   ArraySetAsSeries(haLowArr,   false);
   ArraySetAsSeries(haCloseArr, false);
   ArraySetAsSeries(haPriceArr, false);

   double prevHAOpen  = 0.0;
   double prevHAClose = 0.0;

   for(int i = 0; i < copied; i++)
   {
      double haClose =
         (
            rates[i].open +
            rates[i].high +
            rates[i].low +
            rates[i].close
         ) / 4.0;

      double haOpen;

      if(i == 0)
      {
         haOpen =
            (rates[i].open + rates[i].close)
            / 2.0;
      }
      else
      {
         haOpen =
            (prevHAOpen + prevHAClose)
            / 2.0;
      }

      double haHigh =
         MathMax(
            rates[i].high,
            MathMax(haOpen, haClose)
         );

      double haLow =
         MathMin(
            rates[i].low,
            MathMin(haOpen, haClose)
         );

      haOpenArr[i]  = haOpen;
      haHighArr[i]  = haHigh;
      haLowArr[i]   = haLow;
      haCloseArr[i] = haClose;

      haPriceArr[i] =
         Heiken_GetAppliedPrice(
            haOpen,
            haHigh,
            haLow,
            haClose
         );

      prevHAOpen  = haOpen;
      prevHAClose = haClose;
   }

   // Latest fully closed candle
   closedIndex = copied - 2;

   return (closedIndex >= 1);
}

bool Heiken_CalculateMAAt(const double &values[],
                          int index,
                          int period,
                          ENUM_MA_METHOD method,
                          double &result)
{
   if(period <= 0 ||
      index < period - 1)
      return false;

   if(method == MODE_SMA)
   {
      double sum = 0.0;
      int first = index - period + 1;

      for(int i = first; i <= index; i++)
         sum += values[i];

      result = sum / period;
      return true;
   }

   if(method == MODE_LWMA)
   {
      double weightedSum = 0.0;
      double weightTotal = 0.0;
      int first = index - period + 1;
      int weight = 1;

      for(int i = first;
          i <= index;
          i++, weight++)
      {
         weightedSum += values[i] * weight;
         weightTotal += weight;
      }

      if(weightTotal <= 0.0)
         return false;

      result = weightedSum / weightTotal;
      return true;
   }

   double seed = 0.0;

   for(int i = 0; i < period; i++)
      seed += values[i];

   double ma = seed / period;

   if(index == period - 1)
   {
      result = ma;
      return true;
   }

   if(method == MODE_EMA)
   {
      double alpha =
         2.0 / (period + 1.0);

      for(int i = period;
          i <= index;
          i++)
      {
         ma =
            alpha * values[i] +
            (1.0 - alpha) * ma;
      }

      result = ma;
      return true;
   }

   if(method == MODE_SMMA)
   {
      for(int i = period;
          i <= index;
          i++)
      {
         ma =
            (
               ma * (period - 1) +
               values[i]
            ) / period;
      }

      result = ma;
      return true;
   }

   return false;
}

bool Heiken_GetMAValues(double &fastClosed,
                        double &fastPrev,
                        double &slowClosed,
                        double &slowPrev)
{
   double haOpenArr[];
   double haHighArr[];
   double haLowArr[];
   double haCloseArr[];
   double haPriceArr[];

   int closedIndex = -1;

   int minimumBarsRequired =
      HEIKEN_SLOW_MA + 3;

   if(!Heiken_BuildSeries(
         haOpenArr,
         haHighArr,
         haLowArr,
         haCloseArr,
         haPriceArr,
         closedIndex,
         minimumBarsRequired))
      return false;

   int prevIndex = closedIndex - 1;

   if(!Heiken_CalculateMAAt(
         haPriceArr,
         closedIndex,
         HEIKEN_FAST_MA,
         g_haMAMethod_Heiken,
         fastClosed))
      return false;

   if(!Heiken_CalculateMAAt(
         haPriceArr,
         prevIndex,
         HEIKEN_FAST_MA,
         g_haMAMethod_Heiken,
         fastPrev))
      return false;

   if(!Heiken_CalculateMAAt(
         haPriceArr,
         closedIndex,
         HEIKEN_SLOW_MA,
         g_haMAMethod_Heiken,
         slowClosed))
      return false;

   if(!Heiken_CalculateMAAt(
         haPriceArr,
         prevIndex,
         HEIKEN_SLOW_MA,
         g_haMAMethod_Heiken,
         slowPrev))
      return false;

   return true;
}

bool Heiken_IsCrossUp(double fastClosed,
                      double fastPrev,
                      double slowClosed,
                      double slowPrev)
{
   return (
      fastPrev <= slowPrev &&
      fastClosed > slowClosed
   );
}

bool Heiken_IsCrossDown(double fastClosed,
                        double fastPrev,
                        double slowClosed,
                        double slowPrev)
{
   return (
      fastPrev >= slowPrev &&
      fastClosed < slowClosed
   );
}

void Init_Heiken()
{
   g_lastBar_Heiken = iTime(_Symbol, HEIKEN_TF, 0);
}

void LogConfig_Heiken()
{
   Print(
      "Heiken FIXED | TF=M15 | Fast=12 | Slow=26 | MaxSpread=1000 | Magic=",
      MAGIC_HEIKEN
   );
}

void EnforceDisabled_Heiken(bool enabled, double lots)
{
   if(!enabled || NormalizeLots(lots) <= 0.0)
   {
      CloseAllPositionsByMagic(
         MAGIC_HEIKEN,
         HEIKEN_DEVIATION_POINTS,
         "Heiken"
      );
   }
}

void Process_Heiken(bool enabled, double lots)
{
   if(!IsNewBarForTimeframe(HEIKEN_TF, g_lastBar_Heiken))
      return;

   if(!enabled)
      return;

   double fastClosed = 0.0;
   double fastPrev   = 0.0;
   double slowClosed = 0.0;
   double slowPrev   = 0.0;

   if(!Heiken_GetMAValues(
         fastClosed,
         fastPrev,
         slowClosed,
         slowPrev))
   {
      Print("Heiken MA calculation failed or insufficient data.");
      return;
   }

   bool crossUp =
      Heiken_IsCrossUp(
         fastClosed,
         fastPrev,
         slowClosed,
         slowPrev
      );

   bool crossDown =
      Heiken_IsCrossDown(
         fastClosed,
         fastPrev,
         slowClosed,
         slowPrev
      );

   if(crossDown)
   {
      CloseAllPositionsByMagic(
         MAGIC_HEIKEN,
         HEIKEN_DEVIATION_POINTS,
         "Heiken"
      );
      return;
   }

   if(crossUp)
   {
      double normLot = NormalizeLots(lots);
      if(normLot <= 0.0)
         return;

      if(!Heiken_TradingDayAllowed())
         return;

      if(!Heiken_SpreadOK())
         return;

      if(CountPositionsByMagic(MAGIC_HEIKEN) > 0)
         return;

      OpenBuyByMagic(
         MAGIC_HEIKEN,
         normLot,
         HEIKEN_DEVIATION_POINTS,
         "Heiken_MA_12_26"
      );
   }
}
