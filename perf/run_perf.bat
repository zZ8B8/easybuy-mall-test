@echo off
rem  ============================================================
rem  ASCII ONLY on purpose: cmd.exe mis-parses UTF-8 bytes inside
rem  .bat files. Chinese explanations live in perf/README.md.
rem  ============================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem --- JMeter JVM memory (the default 1G heap fails on small pagefiles) ---
if not defined HEAP set HEAP=-Xms128m -Xmx384m -XX:MaxMetaspaceSize=128m

set "JM="
if defined JMETER_HOME if exist "%JMETER_HOME%\bin\jmeter.bat" set "JM=%JMETER_HOME%\bin\jmeter.bat"
if not defined JM for /f "delims=" %%P in ('where jmeter 2^>nul') do if not defined JM set "JM=%%P"
if not defined JM (
  echo.
  echo [ERROR] Apache JMeter not found.
  echo         Download 5.6.x from https://jmeter.apache.org/download_jmeter.cgi,
  echo         unzip it, then either add its bin folder to PATH
  echo         or set JMETER_HOME to the unzipped folder.
  echo.
  pause
  exit /b 1
)

echo Using JMeter : %JM%
echo Result folder: %~dp0results
echo.

rem --- make sure the demo accounts (user_01..user_30) exist ---
echo [0/3] preparing demo data ...
python "%~dp0..\demo_data.py"

call :run run-1    1 30   "single thread baseline"
call :run run-a   20 40   "20 concurrent users"
call :run run-b   50 40   "50 concurrent users"

echo.
echo All done. Raw results are in perf\results, see docs\07-performance-report.md
pause
exit /b 0

:run
echo [%1] threads=%2 loops=%3 - %4
set HEAP=%HEAP%
call "%JM%" -n -t "%~dp0easybuy-perf.jmx" -l "%~dp0results\%1.jtl" -j "%~dp0results\%1.log" -Jthreads=%2 -Jloops=%3
goto :eof
