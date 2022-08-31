@REM if "%1"=="hide" goto begin
@REM start mshta vbscript:createobject("wscript.shell").run("""%~0"" hide",0)(window.close)&&exit
@REM :begin

@ECHO OFF & PUSHD %~DP0 & cd /d "%~dp0"
%1 %2
mshta vbscript:createobject("shell.application").shellexecute("%~s0","goto :runas","","runas",0)(window.close)&goto :eof
:runas
@REM https://blog.csdn.net/sanqima/article/details/37818115
setlocal enableDelayedExpansion

@REM cleann workspace
call :cleanworkspace

@REM setting workspace
set dest="your clash path"

@REM download clash dashboard and etc
@REM with wget
@REM wget "https://release.dreamacro.workers.dev/latest/clash-windows-amd64-latest.zip" -o "!temp!\clash.zip"
@REM wget "https://github.com/Hackl0us/GeoIP2-CN/raw/release/Country.mmdb" -o "!temp!\Country.mmdb"
@REM wget "https://github.com/Dreamacro/clash-dashboard/archive/refs/heads/gh-pages.zip" -o "!temp!\dashboard.zip"

@REM with curl
curl.exe --retry 5 -s -L -C - -o "!temp!\dashboard.zip" "https://github.com/Dreamacro/clash-dashboard/archive/refs/heads/gh-pages.zip"
curl.exe --retry 5 -s -L -C - -o "!temp!\Country.mmdb" "https://github.com/Hackl0us/GeoIP2-CN/raw/release/Country.mmdb"
curl.exe --retry 5 -s -L -C - -o "!temp!\clash.zip" "https://release.dreamacro.workers.dev/latest/clash-windows-amd64-latest.zip"

@REM unzip
tar -xzf "!temp!\clash.zip" -C !temp!
tar -xzf "!temp!\dashboard.zip" -C !temp!

@REM clean workspace
del /f /q "!temp!\clash.zip" "!temp!\dashboard.zip"

@REM rename file
ren "!temp!\clash-dashboard-gh-pages" dashboard
ren "!temp!\clash-windows-amd64.exe" clash.exe

@REM judge file changed with md5
set "ORIGINAL=" & for /F "skip=1 delims=" %%H in ('
    2^> nul CertUtil -hashfile "!temp!\clash.exe" MD5
') do if not defined ORIGINAL set "ORIGINAL=%%H"

set "RECEIVED=" & for /F "skip=1 delims=" %%H in ('
    2^> nul CertUtil -hashfile "!dest!\clash.exe" MD5
') do if not defined RECEIVED set "RECEIVED=%%H"

if "!ORIGINAL!"=="!RECEIVED!" (
    set "ORIGINAL=" & for /F "skip=1 delims=" %%H in ('
    2^> nul CertUtil -hashfile "!temp!\Country.mmdb" MD5
    ') do if not defined ORIGINAL set "ORIGINAL=%%H"

    set "RECEIVED=" & for /F "skip=1 delims=" %%H in ('
        2^> nul CertUtil -hashfile "!dest!\Country.mmdb" MD5
    ') do if not defined RECEIVED set "RECEIVED=%%H"

    if "!ORIGINAL!" NEQ "!RECEIVED!" (
        set CHANGED=1
    ) else (
        set CHANGED=0
    )
) else (
    set CHANGED=1
)

@REM no new version found
if !CHANGED! EQU 0 (
    del /f /q "!temp!\clash.exe" "!temp!\Country.mmdb"
    rd "!temp!\dashboard" /s /q
    exit /b 1
)

@REM file missing
if not exist "!temp!\clash.exe" goto terminate
if not exist "!temp!\Country.mmdb" goto terminate
if not exist "!temp!\dashboard" goto terminate

@REM stop clash
tasklist | findstr /i "clash.exe" & taskkill /im "clash.exe" /f
del /f /q "!dest!\clash.exe" "!dest!\Country.mmdb"
rd "!dest!\dashboard" /s /q

@REM mv clash to directoy
move "!temp!\clash.exe" !dest!
move "!temp!\Country.mmdb" !dest!
xcopy "!temp!\dashboard" "!dest!\dashboard" /h /e /y /q /i

@REM delete source dashboard
rd "!temp!\dashboard" /s /q

@REM startup clash
"!dest!\clash.exe" -d !dest! -f "!dest!\config.yaml"
goto :eof

@REM delete if file exists
:cleanworkspace
if exist "!temp!\clash.zip" del /f /q "!temp!\clash.zip" 
if exist "!temp!\clash.exe" del /f /q "!temp!\clash.exe" 
if exist "!temp!\dashboard.zip" del /f /q "!temp!\dashboard.zip"
if exist "!temp!\Country.mmdb" del /f /q "!temp!\Country.mmdb"
if exist "!temp!\clash-windows-amd64.exe" del /f /q "!temp!\clash-windows-amd64.exe"

@REM delete directory
if exist "!temp!\clash-dashboard-gh-pages" rd "!temp!\clash-dashboard-gh-pages" /s /q
if exist "!temp!\dashboard" rd "!temp!\dashboard" /s /q
goto :eof

@REM define exit function
:terminate
ECHO "update error, file clash.exe Country.mmdb or dashboard missing"
call :cleanworkspace
exit /b 1
goto :eof

endlocal