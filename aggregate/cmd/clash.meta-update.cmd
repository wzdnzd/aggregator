@REM if "%1"=="hide" goto begin
@REM start mshta vbscript:createobject("wscript.shell").run("""%~0"" hide",0)(window.close)&&exit
@REM :begin

@ECHO OFF & PUSHD %~DP0 & cd /d "%~dp0"
%1 %2
mshta vbscript:createobject("shell.application").shellexecute("%~s0","goto :runas","","runas",0)(window.close)&goto :eof
:runas
@REM https://blog.csdn.net/sanqima/article/details/37818115
setlocal enableDelayedExpansion

@REM setting workspace
set "dest=your clash path"
set "geosite=GeoSite.dat"
set "geoip=GeoIP.dat"
set "clashname=Clash.Meta-windows-amd64.exe"

@REM cleann workspace
call :cleanworkspace

@REM get clash download url
for /f "tokens=1* delims=:" %%a in ('curl --retry 5 -s -L "https://api.github.com/repos/MetaCubeX/Clash.Meta/releases?prerelease=true&per_page=1" ^| findstr /i /r "https://github.com/MetaCubeX/Clash.Meta/releases/download/Prerelease-Alpha/Clash.Meta-windows-amd64-alpha-.*.zip"') do set "DOWNLOADURL=%%b"

if !DOWNLOADURL! == "" goto terminate
set "DOWNLOADURL=!DOWNLOADURL:~2,-1!"
set "GHPROXY=https://ghproxy.com"

@REM with curl
@REM curl.exe --retry 5 -s -L -C - -o "!temp!\dashboard.zip" "!GHPROXY!/https://github.com/Dreamacro/clash-dashboard/archive/gh-pages.zip"
@REM curl.exe --retry 5 -s -L -C - -o "!temp!\!geosite!" "!GHPROXY!/https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/release/geosite.dat"
curl.exe --retry 5 -s -L -C - -o "!temp!\!geosite!" "!GHPROXY!/https://raw.githubusercontent.com/Loyalsoldier/domain-list-custom/release/geosite.dat"
curl.exe --retry 5 -s -L -C - -o "!temp!\!geoip!" "!GHPROXY!/https://raw.githubusercontent.com/Loyalsoldier/geoip/release/geoip-only-cn-private.dat"
curl.exe --retry 5 -s -L -C - -o "!temp!\clash.zip" "!GHPROXY!/!DOWNLOADURL!"

@REM unzip
tar -xzf "!temp!\clash.zip" -C !temp!
@REM tar -xzf "!temp!\dashboard.zip" -C !temp!

@REM clean workspace
@REM del /f /q "!temp!\clash.zip" "!temp!\dashboard.zip"
del /f /q "!temp!\clash.zip"

@REM rename file
@REM ren "!temp!\clash-dashboard-gh-pages" dashboard
ren "!temp!\!clashname!" clash.exe

@REM judge file changed with md5
set "filenames=clash.exe;!geosite!;!geoip!"

for %%a in (!filenames!) do (
    set "ORIGINAL=" & for /F "skip=1 delims=" %%H in ('2^> nul CertUtil -hashfile "!temp!\%%a" MD5') do if not defined ORIGINAL set "ORIGINAL=%%H"

    set "RECEIVED=" & for /F "skip=1 delims=" %%H in ('2^> nul CertUtil -hashfile "!dest!\%%a" MD5') do if not defined RECEIVED set "RECEIVED=%%H"

    if "!ORIGINAL!" NEQ "!RECEIVED!" goto upgrade
)

@REM no new version found
goto cleanworkspace

:upgrade
@REM file missing
if not exist "!temp!\clash.exe" goto terminate
if not exist "!temp!\!geosite!" goto terminate
if not exist "!temp!\!geoip!" goto terminate
@REM if not exist "!temp!\dashboard" goto terminate

@REM stop clash
tasklist | findstr /i "clash.exe" & taskkill /im "clash.exe" /f
del /f /q "!dest!\clash.exe" "!dest!\!geosite!" "!dest!\!geoip!"
@REM rd "!dest!\dashboard" /s /q

@REM mv clash to directoy
move "!temp!\clash.exe" !dest!
move "!temp!\!geosite!" !dest!
move "!temp!\!geoip!" !dest!
@REM xcopy "!temp!\dashboard" "!dest!\dashboard" /h /e /y /q /i

@REM delete source dashboard
@REM rd "!temp!\dashboard" /s /q

@REM startup clash
"!dest!\clash.exe" -d !dest! -f "!dest!\config.yaml"
goto :eof

@REM delete if file exists
:cleanworkspace
if exist "!temp!\clash.zip" del /f /q "!temp!\clash.zip" 
if exist "!temp!\clash.exe" del /f /q "!temp!\clash.exe" 
if exist "!temp!\dashboard.zip" del /f /q "!temp!\dashboard.zip"
if exist "!temp!\!geosite!" del /f /q "!temp!\!geosite!"
if exist "!temp!\!geoip!" del /f /q "!temp!\!geoip!"
if exist "!temp!\!clashname!" del /f /q "!temp!\!clashname!"

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