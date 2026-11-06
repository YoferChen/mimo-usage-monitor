@echo off
rem ============================================================
rem  MiMo Token Plan 用量监控 - 启动管理脚本
rem  双击运行：弹出菜单，选择 启动 / 重启 / 停止 / 查看日志 等
rem  服务在后台运行（无窗口），日志写入 logs\mimo-monitor.log
rem  命令行用法：start.bat start / restart / stop / status / log / tail / clear
rem ============================================================
chcp 936 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title MiMo 用量监控 - 管理菜单
cd /d "%~dp0"

set "APP_HOME=%~dp0"
if "%APP_HOME:~-1%"=="\" set "APP_HOME=%APP_HOME:~0,-1%"
set "MODULE=mimo_usage_monitor"
set "LOG_DIR=%APP_HOME%\logs"
set "LOG_FILE=%LOG_DIR%\mimo-monitor.log"
set "TMP_PID=%LOG_DIR%\.pid.tmp"
set "PYTHONIOENCODING=gbk"
set "CLI_MODE="
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

call :detect_python
if not defined LAUNCHER goto no_python

if not "%~1"=="" (
    set "CLI_MODE=1"
    set "ACTION=%~1"
    goto cli_action
)

:menu
cls
echo.
echo   =========================================
echo    MiMo 用量监控 - 启动管理
echo   =========================================
echo.
call :find_pid
if defined PID (
    echo    状态 : 正在运行  [PID %PID%]
) else (
    echo    状态 : 未运行
)
echo    启动 : %LAUNCHER% ^| %LAUNCH_MODE%
echo    日志 : %LOG_FILE%
echo.
echo    [1] 启动服务
echo    [2] 重启服务
echo    [3] 停止服务
echo    [4] 查看状态
echo    [5] 查看日志（最近 60 行）
echo    [6] 实时跟踪日志
echo    [7] 清空日志
echo    [0] 退出
echo.
choice /c 12345670 /n /m "  请选择 [0-7]: "
if errorlevel 8 goto do_exit
if errorlevel 7 goto do_clear
if errorlevel 6 goto do_tail
if errorlevel 5 goto do_log
if errorlevel 4 goto do_status
if errorlevel 3 goto do_stop
if errorlevel 2 goto do_restart
if errorlevel 1 goto do_start
goto menu

:cli_action
if /i "%ACTION%"=="start" goto do_start
if /i "%ACTION%"=="restart" goto do_restart
if /i "%ACTION%"=="stop" goto do_stop
if /i "%ACTION%"=="status" goto do_status
if /i "%ACTION%"=="log" goto do_log
if /i "%ACTION%"=="tail" goto do_tail
if /i "%ACTION%"=="clear" goto do_clear
echo 用法: %~nx0 start / restart / stop / status / log / tail / clear
echo       不带参数运行则进入交互菜单。
exit /b 1

rem ---------------- 各项操作 ----------------

:do_start
echo.
call :find_pid
if defined PID (
    echo  [提示] 服务已在运行（PID %PID%），如需重启请选择 [2]。
    goto pause_back
)
call :start_service
goto pause_back

:do_restart
echo.
call :find_pid
if defined PID (
    echo  [提示] 正在停止旧进程（PID %PID%）...
    taskkill /PID %PID% /F /T >nul 2>&1
    call :delay 2
)
call :start_service
goto pause_back

:do_stop
echo.
call :find_pid
if not defined PID (
    echo  [提示] 服务未在运行。
    goto pause_back
)
echo  [提示] 正在停止服务（PID %PID%）...
taskkill /PID %PID% /F /T >nul 2>&1
call :delay 2
call :find_pid
if defined PID (
    echo  [失败] 服务未能停止（PID %PID%）。
) else (
    echo  [成功] 服务已停止。
)
goto pause_back

:do_status
cls
echo.
echo  ==== 运行状态 ====
call :find_pid
if defined PID (
    echo  服务正在运行（PID %PID%）
) else (
    echo  服务未运行
)
echo  启动方式 : %LAUNCHER%（%LAUNCH_MODE%）
echo  日志文件 : %LOG_FILE%
if exist "%LOG_FILE%" (
    echo.
    echo  ---- 最近日志 ----
    powershell -NoProfile -Command "Get-Content -Path '%LOG_FILE%' -Tail 5 -Encoding Default"
)
goto pause_back

:do_log
cls
echo.
if not exist "%LOG_FILE%" (
    echo  [提示] 暂无日志文件，请先启动服务。
) else (
    powershell -NoProfile -Command "Get-Content -Path '%LOG_FILE%' -Tail 60 -Encoding Default"
)
goto pause_back

:do_tail
cls
echo.
if not exist "%LOG_FILE%" (
    echo  [提示] 暂无日志文件，请先启动服务。
    goto pause_back
)
echo  [提示] 实时跟踪日志中，按 Ctrl+C 结束。
echo         若提示“终止批处理操作”，请选 N 返回菜单。
echo.
powershell -NoProfile -Command "Get-Content -Path '%LOG_FILE%' -Tail 30 -Wait -Encoding Default"
goto menu

:do_clear
call :find_pid
if defined PID (
    echo  [提示] 服务运行中，日志文件被占用，无法清空。请先停止服务再清空。
    goto pause_back
)
del /q "%LOG_FILE%" >nul 2>&1
if exist "%LOG_FILE%" (
    echo  [失败] 日志文件被占用，无法清空。
) else (
    echo  [成功] 日志已清空。
)
goto pause_back

:do_exit
echo.
echo  [提示] 已退出管理菜单，服务在后台继续运行。
exit /b 0

rem ---------------- 启动与探测 ----------------

:start_service
echo  [提示] 正在后台启动 %MODULE% ...
echo.>>"%LOG_FILE%"
echo ========== 启动 %date% %time% ========= 1>>"%LOG_FILE%"
if "%LAUNCH_KIND%"=="gui" (
    start "" /b "%LAUNCHER%" -m %MODULE% 1>>"%LOG_FILE%" 2>&1
) else (
    start "mimo-monitor" /min "%LAUNCHER%" -m %MODULE% 1>>"%LOG_FILE%" 2>&1
)
call :delay 3
call :find_pid
if defined PID (
    echo  [成功] 服务已在后台启动（PID %PID%）。
) else (
    echo  [失败] 服务未能保持运行，请选择 [5] 查看日志排查。
)
goto :eof

:detect_python
set "LAUNCHER="
set "LAUNCH_KIND="
set "LAUNCH_MODE="
call :try_gui pythonw
call :try_gui pyw
call :try_console python
call :try_console py
goto :eof

:try_gui
if defined LAUNCHER goto :eof
where %1 >nul 2>&1
if errorlevel 1 goto :eof
set "LAUNCHER=%1"
set "LAUNCH_KIND=gui"
set "LAUNCH_MODE=后台隐藏运行"
goto :eof

:try_console
if defined LAUNCHER goto :eof
where %1 >nul 2>&1
if errorlevel 1 goto :eof
set "LAUNCHER=%1"
set "LAUNCH_KIND=console"
set "LAUNCH_MODE=后台运行，附带最小化窗口"
goto :eof

:find_pid
set "PID="
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^py' -and $_.CommandLine -match 'mimo_usage_monitor' } | Select-Object -First 1 -ExpandProperty ProcessId | Out-File -FilePath '%TMP_PID%' -Encoding ascii" >nul 2>&1
if exist "%TMP_PID%" set /p PID=<"%TMP_PID%"
del "%TMP_PID%" >nul 2>&1
goto :eof

:delay
ping -n %~1 127.0.0.1 >nul 2>&1
goto :eof

:pause_back
if defined CLI_MODE exit /b 0
echo.
pause
goto menu

:no_python
echo.
echo  [错误] 未找到可用的 Python（pythonw / pyw / python / py）。
echo         请安装 Python 3.10 及以上版本并将其加入 PATH。
echo.
pause
exit /b 1
