@REM author: wzdnzd
@REM date: 2022-08-24
@REM describe: auto update clash, geosite.dat, geoip.dat

@echo off & PUSHD %~DP0 & cd /d "%~dp0"

@REM change encoding
@REM chcp 65001

@REM https://blog.csdn.net/sanqima/article/details/37818115
setlocal enableDelayedExpansion

@REM batch file name
set "batname=%~nx0"

@REM help flag
set "helpflag=0"

@REM only reload
set "reloadonly=0"

@REM use clash.meta
set "clashmeta=0"

@REM alpha version allowed
set "alpha=0"

@REM yacd dashboard, see https://github.com/MetaCubeX/Yacd-meta
set "yacd=0"

@REM parse arguments
call :argsparse %*

if "!helpflag!" == "1" (
    exit /b 0
)

@REM run as admin
cacls "%SystemDrive%\System Volume Information" >nul 2>&1 || (start "" mshta vbscript:CreateObject^("Shell.Application"^).ShellExecute^("%~snx0"," %*","","runas",0^)^(window.close^)&exit /b)

@REM setting workspace
set "dest=your clash path"

@REM config file path
set "configfile=!dest!\\config.yaml"

@REM exit if config file not exists
if not exist "!configfile!" (
    exit /b 1
)

if "!reloadonly!" == "1" goto :reload

@REM github proxy
set "ghproxy=https://ghproxy.com"

@REM dashboard directory name
call :extractpath

@REM confirm download url and filename
call :clashversion

@REM confirm donwload url
call :confirmurl

@REM cleann workspace
call :cleanworkspace "!temp!"

@REM update dashboard
call :dashboardupdate

@REM update rulefiles
call :updaterules

@REM download clah.exe and geoip.data and so on
call :donwloadfiles

@REM judge file changed with md5
for %%a in (!filenames!) do (
    @REM found new file
    if not exist "!dest!\\%%a" goto :upgrade

    set "original=" & for /F "skip=1 delims=" %%h in ('2^> nul CertUtil -hashfile "!temp!\\%%a" MD5') do if not defined original set "original=%%h"

    set "received=" & for /F "skip=1 delims=" %%h in ('2^> nul CertUtil -hashfile "!dest!\\%%a" MD5') do if not defined received set "received=%%h"

    if "!original!" NEQ "!received!" goto :upgrade
)

@REM no new version found
echo don't need update due to not found new version
goto :cleanworkspace "!temp!"

@REM parse and validate arguments
:argsparse
set result=false
if "%1" == "-h" set result=true
if "%1" == "--help" set result=true
if "%result%" == "true" (
    call :usage
)

if "%1" == "-r" set result=true
if "%1" == "--reload" set result=true
if "%result%" == "true" (
    set "reloadonly=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-m" set result=true
if "%1" == "--meta" set result=true
if "%result%" == "true" (
    set "clashmeta=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-a" set result=true
if "%1" == "--alpha" set result=true
if "%result%" == "true" (
    set "alpha=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-y" set result=true
if "%1" == "--yacd" set result=true
if "%result%" == "true" (
    set "yacd=1"
    set result=false
    shift & goto :argsparse
)

if "%1" NEQ "" (
    @echo argument error, unknown: %1, enable: -a -h -m -r -y
    @echo.
    goto :usage
)

goto :eof


@REM help
:usage
@echo Usage: !batname! [OPTIONS]
@echo.
@echo arguments: support long options and short options
@echo -h, --help           display this help and exit
@echo -r, --reload         reload config only
@echo -m, --meta           use clash.meta instead of clash premium, 
@echo -a, --alpha          alpha version allowed if using clash.meta, the stable version is used by default
@echo -y, --yacd           use yacd to replace the standard dashboard

set "helpflag=1"
goto :eof

@REM confirm download url and filename according parameters
:clashversion
set "content="
set "geositeneed=0"

for /f "tokens=*" %%i in ('findstr /i /r "GEOSITE,.*" !configfile!') do set "content=!content!;%%i"
call :searchrules "!content!"

@REM rulesets include GEOSITE, must be clash.meta
if "!notfound!" == "0" (
    set "clashmeta=1"
    set "geositeneed=1"
    goto :eof
)

set "content="
for /f "tokens=*" %%i in ('findstr /i /r "SCRIPT,.*" !configfile!') do set "content=!content!;%%i"
call :searchrules "!content!"

@REM rulesets include SCRIPT, must be clash.premium
if "!notfound!" == "0" (
    set "clashmeta=0"
)

goto :eof

@REM check if special rules are included
:searchrules
set "rulesets=%~1"
set "notfound=1"

for /F "tokens=1* delims=;" %%f in ("!rulesets!") do (
    set "rule=%%f"
    if /i "!rule:~0,1!"=="-" (
        set "notfound=0"
        goto :eof
    )

    if "%%g" NEQ "" call :searchrules "%%g"
)

goto :eof

@REM download binary file and data
:donwloadfiles
set "filenames="

@REM download clash
if "!clashurl!" NEQ "" (
    curl.exe --retry 5 -s -L -C - -o "!temp!\\clash.zip" "!clashurl!"

    if exist "!temp!\\clash.zip" (
        @REM unzip
        tar -xzf "!temp!\\clash.zip" -C !temp!

        @REM clean workspace
        del /f /q "!temp!\\clash.zip"
    )

    if exist "!temp!\\!clashexe!" (
        @REM rename file
        ren "!temp!\\!clashexe!" clash.exe

        set "filenames=clash.exe"
    )
)

@REM download Country.mmdb
if "!countryurl!" NEQ "" (
    curl.exe --retry 5 -s -L -C - -o "!temp!\\!countryfile!" "!countryurl!"

    if exist "!temp!\\!countryfile!" (
        if "!filenames!" == "" (
            set "filenames=!countryfile!"
        ) else (
            set "filenames=!filenames!;!countryfile!"
        )
    )
)

@REM download GeoSite.dat
if "!geositeurl!" NEQ "" (
    curl.exe --retry 5 -s -L -C - -o "!temp!\\!geositefile!" "!geositeurl!"

    if exist "!temp!\\!geositefile!" (
        if "!filenames!" == "" (
            set "filenames=!geositefile!"
        ) else (
            set "filenames=!filenames!;!geositefile!"
        )
    )
)

@REM download GeoIP.dat
if "!geoipurl!" NEQ "" (
    curl.exe --retry 5 -s -L -C - -o "!temp!\\!geoipfile!" "!geoipurl!"

    if exist "!temp!\\!geoipfile!" (
        if "!filenames!" == "" (
            set "filenames=!geoipfile!"
        ) else (
            set "filenames=!filenames!;!geoipfile!"
        )
    )
)

echo filenames: !filenames!
goto :eof

@REM update clash.exe and data
:upgrade
@REM make sure the file exists
set "existfiles="
for %%a in (!filenames!) do (
    if exist "!temp!\\%%a" (
        if "!existfiles!" == "" (
            set "existfiles=%%a"
        ) else (
            set "existfiles=!existfiles!;%%a"
        )
    )
)

@REM file missing
if "!existfiles!" == "" goto :terminate

@REM stop clash
tasklist | findstr /i "clash.exe" >nul 2>nul && taskkill /im "clash.exe" /f

@REM waiting for release
timeout /t 1

@REM copy file
for %%a in (!filenames!) do (
    set "filename=%%a"

    @REM delete if old file exists
    if exist "!dest!\\!filename!" (
        del /f /q "!dest!\\!filename!" >nul 2>nul
    )
    
    @REM move new file to dest
    move "!temp!\\!filename!" !dest!
)

@REM startup clash
"!dest!\\clash.exe" -d !dest! -f "!configfile!"
goto :eof

@REM donwload url
:confirmurl
@REM country data
set "countryurl=https://raw.githubusercontent.com/Hackl0us/GeoIP2-CN/release/Country.mmdb"

@REM geosite/geoip filename
set "countryfile=Country.mmdb"
set "geositefile=GeoSite.dat"
set "geoipfile=GeoIP.dat"

@REM dashboard url
set "dashboardurl=https://github.com/Dreamacro/clash-dashboard/archive/refs/heads/gh-pages.zip"
set "dashdirectory=clash-dashboard-gh-pages"

if "!clashmeta!" == "0" (
    set "clashurl=https://release.dreamacro.workers.dev/latest/clash-windows-amd64-latest.zip"
    set "clashexe=clash-windows-amd64.exe"

    if "!yacd!" == "1" (
        set "dashboardurl=https://github.com/haishanh/yacd/archive/refs/heads/gh-pages.zip"
        set "dashdirectory=yacd-gh-pages"
    )
) else (
    set "clashexe=Clash.Meta-windows-amd64.exe"
    set "geositeurl=https://raw.githubusercontent.com/Loyalsoldier/domain-list-custom/release/geosite.dat"
    set "geoipurl=https://raw.githubusercontent.com/Loyalsoldier/geoip/release/geoip-only-cn-private.dat"

    if "!alpha!" == "1" (
        for /f "tokens=1* delims=:" %%a in ('curl --retry 5 -s -L "https://api.github.com/repos/MetaCubeX/Clash.Meta/releases?prerelease=true&per_page=10" ^| findstr /i /r "https://github.com/MetaCubeX/Clash.Meta/releases/download/Prerelease-Alpha/Clash.Meta-windows-amd64-alpha-.*.zip"') do set "clashurl=%%b"
    ) else (
        for /f "tokens=1* delims=:" %%a in ('curl --retry 5 -s -L "https://api.github.com/repos/MetaCubeX/Clash.Meta/releases/latest?per_page=1" ^| findstr /i /r "https://github.com/MetaCubeX/Clash.Meta/releases/download/.*/Clash.Meta-windows-amd64-.*.zip"') do set "clashurl=%%b"
    )

    if !clashurl! == "" (
        echo cannot extract download url for clash.meta
        goto :eof
    )

    set "clashurl=!clashurl:~2,-1!"

    @REM geodata-mode
    set "geodatamode=false"
    for /f "tokens=1,2 delims=:" %%a in ('findstr /i /r "geodata-mode:.*" !configfile!') do (
        call :trim %%a
        set "mode=!rawtext!"

        @REM commented
        if /i "!mode:~0,1!" NEQ "#" (
            call :trim %%b
            set "geodatamode=!rawtext!"
        )
    )

    @REM geosite.data download url
    if "!geositeneed!" == "0" (
        set "geositeurl="
    ) else (
        for /f "tokens=1* delims=:" %%a in ('findstr /i /r "geosite:.*" !configfile!') do (
            call :trim %%a
            set "geositekey=!rawtext!"

            @REM commented
            if /i "!geositekey:~0,1!" NEQ "#" (
                call :trim %%b
                set "geositeurl=!rawtext!"
            )
        )
    )

    @REM geoip.data
    if "!geodatamode!" == "false" (
        set "geoipurl="

        for /f "tokens=1* delims=:" %%a in ('findstr /i /r "mmdb:.*" !configfile!') do (
            call :trim %%a
            set "mmdbkey=!rawtext!"

            @REM commented
            if /i "!mmdbkey:~0,1!" NEQ "#" (
                call :trim %%b
                set "countryurl=!rawtext!"
            )
        )
    ) else (
        set "countryurl="

        for /f "tokens=1* delims=:" %%a in ('findstr /i /r /c:"geoip:[ ][ ]*http*://" !configfile!') do (
            call :trim %%a
            set "geoipkey=!rawtext!"

            @REM commented
            if /i "!geoipkey:~0,1!" NEQ "#" (
                call :trim %%b
                set "geoipurl=!rawtext!"
            )
        )
    )

    if "!yacd!" == "1" (
        set "dashboardurl=https://github.com/MetaCubeX/Yacd-meta/archive/refs/heads/gh-pages.zip"
        set "dashdirectory=Yacd-meta-gh-pages"
    )
)

@REM don't need dashboard
if "!dashboard!" == "" (
    set "dashboardurl="
)

@REM proxy clashurl
if "!clashurl:~0,18!" == "https://github.com" set "clashurl=!ghproxy!/!clashurl!"
if "!clashurl:~0,33!" == "https://raw.githubusercontent.com" set "clashurl=!ghproxy!/!clashurl!"

@REM proxy dashboardurl
if "!dashboardurl:~0,18!" == "https://github.com" set "dashboardurl=!ghproxy!/!dashboardurl!"
if "!dashboardurl:~0,33!" == "https://raw.githubusercontent.com" set "dashboardurl=!ghproxy!/!dashboardurl!"

@REM proxy countryurl
if "!countryurl:~0,18!" == "https://github.com" set "countryurl=!ghproxy!/!countryurl!"
if "!countryurl:~0,33!" == "https://raw.githubusercontent.com" set "countryurl=!ghproxy!/!countryurl!"

@REM proxy geositeurl
if "!geositeurl:~0,18!" == "https://github.com" set "geositeurl=!ghproxy!/!geositeurl!"
if "!geositeurl:~0,33!" == "https://raw.githubusercontent.com" set "geositeurl=!ghproxy!/!geositeurl!"

@REM proxy geoipurl
if "!geoipurl:~0,18!" == "https://github.com" set "geoipurl=!ghproxy!/!geoipurl!"
if "!geoipurl:~0,33!" == "https://raw.githubusercontent.com" set "geoipurl=!ghproxy!/!geoipurl!"

goto :eof

@REM leading and trailing whitespace
:trim
set "rawtext=%1"

for /f "tokens=* delims= " %%a in ("!rawtext!") do set "rawtext=%%a"
for /l %%a in (1,1,100) do if "!rawtext:~-1!"==" " set "rawtext=!rawtext:~0,-1!"

goto :eof

@REM reload config
:reload
if not exist "!configfile!" goto :eof

@REM clash api address
for /f "tokens=1* delims=:" %%a in ('findstr /i /r "external-controller.*" !configfile!') do set "clashapi=%%b"
set "clashapi=http://!clashapi:~1!/configs?force=true"

@REM clash api secret
for /f "tokens=1* delims=:" %%a in ('findstr /i /r "secret.*" !configfile!') do set "secret=%%b"
set "secret=!secret:~2,-1!"

@REM running detect
tasklist | findstr /i "clash.exe" >nul 2>nul && set "running=1" || set "running=0"

if "!running!" == "1" (
    @REM call api for reload
    curl --retry 5 -s -L -X PUT "!clashapi!" -H "Content-Type: application/json" -H "Authorization: Bearer !secret!" -d "{""path"":""!configfile!""}"
)

goto :eof


@REM update rules
:updaterules
set rules=
set localfiles=

if not exist "!configfile!" goto :eof

@REM rules and file path
for /f "tokens=1* delims=:" %%i in ('findstr /i /r "https://ghproxy.com/.*" !configfile!') do set "rules=!rules!,%%j"
for /f "tokens=1* delims=:" %%i in ('findstr /i /r "rulesets/.*" !configfile!') do set "localfiles=!localfiles!,%%j"

set "changed=0"
for %%u in (!rules!) do (
    call :trim %%u
    set "ruleurl=!rawtext!"
    for /f "tokens=1* delims=," %%r in ("!localfiles!") do (
        if /i "!ruleurl:~0,8!"=="https://" (
            for /f "tokens=1-3 delims=/" %%f in ("%%r") do (
                curl.exe --retry 5 -s -L -C - "!ruleurl!" > "!dest!\\rulesets\\%%h"
                if "!changed!" == "0" set "changed=1"
            )
        )
        
        set "localfiles=%%s"
    )
)

if "!changed!" == "1" goto :reload

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
if "!dashboardurl!" == "" (
    ECHO skip update clash dashboard because it's disable
    goto :eof
)

curl.exe --retry 5 -s -L -C - -o "!temp!\\!dashboard!.zip" "!dashboardurl!"

@REM unzip
tar -xzf "!temp!\\!dashboard!.zip" -C !temp!
del /f /q "!temp!\\!dashboard!.zip"

@REM rename
ren "!temp!\\!dashdirectory!" !dashboard!

@REM replace if dashboard download success
dir /a /s /b "!temp!\\!dashboard!" | findstr . >nul && goto :replacedir || goto :eof

:replacedir
@REM delete old folder if exists
if exist "!dest!\\!dashboard!" rd "!dest!\\!dashboard!" /s /q

@REM copy to dest
xcopy "!temp!\\!dashboard!" "!dest!\\!dashboard!" /h /e /y /q /i

@REM delete source dashboard
rd "!temp!\\!dashboard!" /s /q

goto :eof


@REM delete if file exists
:cleanworkspace
set "directory=%~1"
if "!directory!" == "" set "directory=!temp!"

if exist "!directory!\\clash.zip" del /f /q "!directory!\\clash.zip" 
if exist "!directory!\\clash.exe" del /f /q "!directory!\\clash.exe"

if "!clashexe!" NEQ "" (
    if exist "!directory!\\!clashexe!" del /f /q "!directory!\\!clashexe!"
)

if "!countryfile!" NEQ "" (
    if exist "!directory!\\!countryfile!" del /f /q "!directory!\\!countryfile!"
)

if "!geositefile!" NEQ "" (
    if exist "!directory!\\!geositefile!" del /f /q "!directory!\\!geositefile!"
)

if "!geoipfile!" NEQ "" (
    if exist "!directory!\\!geoipfile!" del /f /q "!directory!\\!geoipfile!"
)

@REM delete directory
if "!dashdirectory!" NEQ "" (
    if exist "!directory!\\!dashdirectory!" rd "!directory!\\!dashdirectory!" /s /q
)

if "!dashboard!" == "" goto :eof
if exist "!directory!\\!dashboard!.zip" del /f /q "!directory!\\!dashboard!.zip"
if exist "!directory!\\!dashboard!" rd "!directory!\\!dashboard!" /s /q

goto :eof


@REM define exit function
:terminate
ECHO update error, file clash.exe Country.mmdb or dashboard missing
call :cleanworkspace "!temp!"
exit /b 1
goto :eof

endlocal