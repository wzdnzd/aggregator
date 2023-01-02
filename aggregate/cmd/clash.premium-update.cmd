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

@REM config file path
set "configfile=!dest!\\config.yaml"

@REM github proxy
set "ghproxy=https://ghproxy.com"

@REM dashboard directory name
call :extractpath

@REM cleann workspace
call :cleanworkspace

@REM update dashboard
call :dashboardupdate

@REM update rulefiles
call :updaterules

@REM download clash and Country.mmdb with curl
curl.exe --retry 5 -s -L -C - -o "!temp!\\Country.mmdb" "!ghproxy!/https://raw.githubusercontent.com/Hackl0us/GeoIP2-CN/release/Country.mmdb"
curl.exe --retry 5 -s -L -C - -o "!temp!\\clash.zip" "https://release.dreamacro.workers.dev/latest/clash-windows-amd64-latest.zip"

@REM unzip
tar -xzf "!temp!\\clash.zip" -C !temp!

@REM clean workspace
del /f /q "!temp!\\clash.zip"

@REM rename file
ren "!temp!\\clash-windows-amd64.exe" clash.exe

@REM judge file changed with md5
set "filenames=clash.exe;Country.mmdb"

for %%a in (!filenames!) do (
    set "ORIGINAL=" & for /F "skip=1 delims=" %%H in ('2^> nul CertUtil -hashfile "!temp!\\%%a" MD5') do if not defined ORIGINAL set "ORIGINAL=%%H"

    set "RECEIVED=" & for /F "skip=1 delims=" %%H in ('2^> nul CertUtil -hashfile "!dest!\\%%a" MD5') do if not defined RECEIVED set "RECEIVED=%%H"

    if "!ORIGINAL!" NEQ "!RECEIVED!" goto upgrade
)

@REM no new version found
goto cleanworkspace

@REM update clash.exe and Country.mmdb
:upgrade
@REM file missing
if not exist "!temp!\\clash.exe" goto terminate
if not exist "!temp!\\Country.mmdb" goto terminate

@REM stop clash
tasklist | findstr /i "clash.exe" & taskkill /im "clash.exe" /f
del /f /q "!dest!\\clash.exe" "!dest!\\Country.mmdb"

@REM mv clash to directoy
move "!temp!\\clash.exe" !dest!
move "!temp!\\Country.mmdb" !dest!

@REM startup clash
"!dest!\\clash.exe" -d !dest! -f "!configfile!"
goto :eof


@REM update rules
:updaterules
set rules=
set localfiles=

if not exist "!configfile!" goto :eof

@REM clash api address
for /f "tokens=1* delims=:" %%a in ('findstr /i /r "external-controller.*" !configfile!') do set "clashapi=%%b"
set "clashapi=http://!clashapi:~1!/configs?force=true"

@REM clash api secret
for /f "tokens=1* delims=:" %%a in ('findstr /i /r "secret.*" !configfile!') do set "secret=%%b"
set "secret=!secret:~2,-1!"

@REM rules and file path
for /f "tokens=1* delims=:" %%i in ('findstr /i /r "https://ghproxy.com/.*" !configfile!') do set "rules=!rules!,%%j"
for /f "tokens=1* delims=:" %%i in ('findstr /i /r "rulesets/.*" !configfile!') do set "localfiles=!localfiles!,%%j"

for %%u in (!rules!) do (
    set "ruleurl=%%u"
    for /F "tokens=1* delims=," %%r in ("!localfiles!") do (
        if /i "!ruleurl:~0,8!"=="https://" (
            for /F "tokens=1-3 delims=/" %%f in ("%%r") do (
                curl.exe --retry 5 -s -L -C - "!ruleurl!" > "!dest!\\rulesets\\%%h"
            )
        )
        
        set "localfiles=%%s"
    )
)

@REM reload
curl --retry 5 -s -L -X PUT "!clashapi!" -H "Content-Type: application/json" -H "Authorization: Bearer !secret!" -d "{""path"":""!configfile!""}"

goto :eof


@REM extract dashboard path
:extractpath
if not exist "!configfile!" (
    set "dashboard="
    goto :eof
)

set "content="
for /f "tokens=*" %%i in ('findstr /i /r "external-ui:.*" !configfile!') do set "content=%%i"

@REM not found 'external-ui' configuration in config file
if "!content!" == "" (
    set "dashboard="
    goto :eof
)

for /f "tokens=1* delims=:" %%a in ('findstr /i /r "external-ui:.*" !configfile!') do (
    set "uikey=%%a"

    @REM commented
    if /i "!uikey:~0,1!"=="#" (
        set "dashboard="
        goto :eof
    )

    set "dashboard=%%b"
    set "dashboard=!dashboard:~1!"
)

goto :eof


@REM upgrade dashboard
:dashboardupdate
if "!dashboard!" == "" (
    ECHO skip update clash dashboard because it's disable
    goto :eof
)

curl.exe --retry 5 -s -L -C - -o "!temp!\\!dashboard!.zip" "!ghproxy!/https://github.com/Dreamacro/clash-dashboard/archive/refs/heads/gh-pages.zip"

@REM unzip
tar -xzf "!temp!\\!dashboard!.zip" -C !temp!
del /f /q "!temp!\\!dashboard!.zip"

@REM rename
ren "!temp!\\clash-dashboard-gh-pages" !dashboard!

@REM delete old folder if exists
if exist "!dest!\\!dashboard!" rd "!dest!\\!dashboard!" /s /q

@REM copy to dest
xcopy "!temp!\\!dashboard!" "!dest!\\!dashboard!" /h /e /y /q /i

@REM delete source dashboard
rd "!temp!\\!dashboard!" /s /q

goto :eof


@REM delete if file exists
:cleanworkspace
if exist "!temp!\\clash.zip" del /f /q "!temp!\\clash.zip" 
if exist "!temp!\\clash.exe" del /f /q "!temp!\\clash.exe" 
if exist "!temp!\\Country.mmdb" del /f /q "!temp!\\Country.mmdb"
if exist "!temp!\\clash-windows-amd64.exe" del /f /q "!temp!\\clash-windows-amd64.exe"

@REM delete directory
if exist "!temp!\\clash-dashboard-gh-pages" rd "!temp!\\clash-dashboard-gh-pages" /s /q

if "!dashboard!" == "" goto :eof

if exist "!temp!\\!dashboard!.zip" del /f /q "!temp!\\!dashboard!.zip"
if exist "!temp!\\!dashboard!" rd "!temp!\\!dashboard!" /s /q

goto :eof


@REM define exit function
:terminate
ECHO update error, file clash.exe Country.mmdb or dashboard missing
call :cleanworkspace
exit /b 1
goto :eof

endlocal