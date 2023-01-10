@REM author: wzdnzd
@REM date: 2022-08-24
@REM describe: network proxy controller for clash

@echo off & PUSHD %~DP0 & cd /d "%~dp0"

@REM change encoding
chcp 65001 >nul 2>nul

@REM https://blog.csdn.net/sanqima/article/details/37818115
setlocal enableDelayedExpansion

@REM output with color
call :setESC

@REM call workflow
goto :workflow


@REM ########################
@REM function define blow ###
@REM ########################

@REM process pipeline
:workflow
@REM batch file name
set "batname=%~nx0"

@REM exit flag
set "shouldexit=0"

@REM init
set "initflag=0"

@REM configuration file name
set "configuration=config.yaml"

@REM subscription link
set "sublink="
set "isweblink=0"

@REM check
set "testflag=0"

@REM repair
set "repair=0"

@REM only reload
set "reloadonly=0"

@REM restart clash.exe
set "restartflag=0"

@REM close proxy
set "killflag=0"

@REM update
set "updateflag=0"

@REM purge
set "purgeflag=0"

@REM only update subscriptions and rulesets
set "quickflag=0"

@REM don't update subscription
set "exclude=0"

@REM use clash.meta
set "clashmeta=0"

@REM alpha version allowed
set "alpha=0"

@REM yacd dashboard, see https://github.com/MetaCubeX/Yacd-meta
set "yacd=0"

@REM run on background
set "asdaemon=0"

@REM show window
set "show=0"

@REM setting workspace
set "dest="

@REM network proxy registry configuration path
set "proxyregpath=HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"

@REM autostart registry configuration path
set "autostartregpath=HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
set "startupapproved=HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"

@REM parse arguments
call :argsparse %*

@REM invalid arguments
if "!shouldexit!" == "1" exit /b 1

@REM regular file path
if "!dest!" == "" set "dest=%~dp0"
call :pathregular dest "!dest!"

@REM auto start vb script
set "startupvbs=!dest!\startup.vbs"

@REM auto update vb script
set "updatevbs=!dest!\update.vbs"

@REM close network proxy
if "!killflag!" == "1" goto :closeproxy

@REM connectivity test
if "!testflag!" == "1" (
    call :checkconnect available 1
    exit /b
)

@REM clean all setting
if "!purgeflag!" == "1" goto :purge

@REM prevent precheck if no action
if "!reloadonly!" == "0" if "!restartflag!" == "0" if "!repair!" == "0" if "!updateflag!" == "0" if "!initflag!" == "0" (
    @echo [%ESC%[91merror%ESC%[0m] must include one action in [%ESC%[97m-f%ESC%[0m %ESC%[97m-i%ESC%[0m %ESC%[97m-k%ESC%[0m %ESC%[97m-r%ESC%[0m %ESC%[97m-t%ESC%[0m %ESC%[97m-u%ESC%[0m]
    @echo.

    if "!shouldexit!" == "0" goto :usage
    exit /b
)

@REM config file path
call :precheck configfile
if "!configfile!" == "" exit /b 1

@REM reload config
if "!reloadonly!" == "1" goto :reload

@REM update
if "!restartflag!" == "1" goto :restartprogram

@REM check issues
if "!repair!" == "1" goto :resolveissues

@REM update
if "!updateflag!" == "1" goto :updateplugins

@REM init
if "!initflag!" == "1" goto :initialize

@REM unknown command
@REM if "!shouldexit!" == "0" goto :usage

exit /b


@REM check if the configuration file exists
:precheck <result>
set "%~1="
set "subfile=!temp!\clashsub.yaml"

@REM absolute path
call :pathconvert conflocation "!configuration!"
call :pathregular conflocation "!conflocation!"
if "!conflocation!" == "" (
    @echo [%ESC%[91merror%ESC%[0m] configuration path is %ESC%[91minvalid%ESC%[0m, the network proxy cannot start
    exit /b 1
)

@REM cannot contain whitespace in path
if "!conflocation!" NEQ "!conflocation: =!" (
    @echo [%ESC%[91merror%ESC%[0m] invalid configuration path "%ESC%[97m!conflocation!%ESC%[0m", %ESC%[91mcannot%ESC%[0m contain %ESC%[97mwhitespace%ESC%[0m
    exit /b 1
)

if "!isweblink!" == "1" (
    if exist "!conflocation!" (
        choice /t 6 /d n /n /m "[%ESC%[97mwarning%ESC%[0m] %ESC%[97mexisting%ESC%[0m configuration file "%ESC%[97m!conflocation!%ESC%[0m" will be %ESC%[91moverwritten%ESC%[0m, do you want to continue? (%ESC%[97mY%ESC%[0m/%ESC%[97mN%ESC%[0m)? "
        if !errorlevel! == 2 exit /b 1
    )

    @REM try to download
    del /f /q "!subfile!" >nul 2>nul

    set "statuscode=000"
    for /f %%a in ('curl --retry 3 --retry-max-time 30 -m 60 --connect-timeout 30 -L -s -o "!subfile!" -w "%%{http_code}" -H "User-Agent: Clash" "!sublink!"') do set "statuscode=%%a"

    @REM download success
    if "!statuscode!" == "200" (
        set "filesize=0"
        if exist "!subfile!" (for %%a in ("!subfile!") do set "filesize=%%~za")
        if !filesize! GTR 64 (
            @REM validate
            set "content="
            for /f "tokens=*" %%a in ('findstr /i /r /c:"^external-controller:[ ][ ]*.*:[0-9][0-9]*.*" !subfile!') do set "content=%%a"
            if "!content!" == "" (
                @echo [%ESC%[91merror%ESC%[0m] invalid configuration file, please confirm the %ESC%[97msubscription%ESC%[0m is valid
                exit /b 1
            )

            del /f /q "!conflocation!" >nul 2>nul
            call :splitpath filepath filename "!conflocation!"
            call :makedirs success "!filepath!"
            if "!success!" == "0" (
                @echo [%ESC%[91merror%ESC%[0m] %ESC%[91mfailed%ESC%[0m to create directory "%ESC%[97m!filepath!%ESC%[0m", please check whether the path is legal
                exit /b 1
            )

            move "!subfile!" "!conflocation!" >nul 2>nul
            @echo [%ESC%[95minfo%ESC%[0m] configuration file has been downloaded %ESC%[95msuccessfully%ESC%[0m
        ) else (
            @REM output is empty
            set "statuscode=000"
        )
    )

    if "!statuscode!" NEQ "200" (
        @echo [%ESC%[91merror%ESC%[0m] configuration file download %ESC%[91mfailed%ESC%[0m, please check if your subscription link is available
        exit /b 1
    )
)

if not exist "!conflocation!" (
    @echo [%ESC%[91merror%ESC%[0m] the specified configuration file "%ESC%[97m!conflocation!%ESC%[0m" does %ESC%[91mnot exist%ESC%[0m
    goto :eof
)

@REM validate
set "content="
for /f "tokens=1* delims=:" %%a in ('findstr /i /r /c:"^proxy-groups:[ ]*" "!conflocation!"') do set "content=%%a"
call :trim content "!content!"
if "!content!" NEQ "proxy-groups" (
    @echo [%ESC%[91merror%ESC%[0m] %ESC%[91minvalid%ESC%[0m configuration file "%ESC%[97m!conflocation!%ESC%[0m"
    exit /b 1
)

set "%~1=!conflocation!"
goto :eof


@REM Initialize network proxy
:initialize
choice /t 5 /d n /n /m "[%ESC%[97mwarning%ESC%[0m] clash will be initialized and started in "%ESC%[97m!dest!%ESC%[0m", do you want to continue (%ESC%[97mY%ESC%[0m/%ESC%[97mN%ESC%[0m)? "
if !errorlevel! == 2 exit /b 1

set "quickflag=0"
set "exclude=1"
call :updateplugins
goto :eof


@REM fix network issues
:resolveissues
@REM mandatory use of the stable version
set "alpha=0"

@echo [%ESC%[95minfo%ESC%[0m] start checking and fixing proxy network problems

@REM check status
call :checkconnect available 0
set "lazycheck=0"
if "!available!" == "1" (
    choice /t 5 /d n /n /m "[%ESC%[97mwarning%ESC%[0m] network proxy is %ESC%[95mworking fine%ESC%[0m, %ESC%[91mno fixes needed%ESC%[0m, do you want to continue (%ESC%[97mY%ESC%[0m/%ESC%[97mN%ESC%[0m)? "
    if !errorlevel! == 2 exit /b 1
) else (
    @REM running detect
    call :isrunning status
    if "!status!" == "0" (
        call :checkwapper continue 1
        if "!continue!" == "0" exit /b
    ) else set "lazycheck=1"
)

@REM O: Reload | R: Restart | U: Restore | N: Cancel
choice /t 6 /c ORUN /d R /n /m "[%ESC%[97mwarning%ESC%[0m] press %ESC%[97mO%ESC%[0m to %ESC%[97mReload%ESC%[0m, press %ESC%[97mR%ESC%[0m to %ESC%[97mRestart%ESC%[0m, press %ESC%[97mU%ESC%[0m to %ESC%[97mRestore%ESC%[0m to default, press %ESC%[97mN%ESC%[0m to %ESC%[97mCancel%ESC%[0m. (%ESC%[97mO%ESC%[0m/%ESC%[97mR%ESC%[0m/%ESC%[97mU%ESC%[0m/%ESC%[97mN%ESC%[0m) "

if !errorlevel! == 1 (
    call :reload
) else if !errorlevel! == 2 (
    call :restartprogram
) else if !errorlevel! == 3 (
    @REM kill clash process
    call :killprocesswrapper

    @REM wait 3 seconds
    timeout /t 3 /nobreak >nul 2>nul

    @REM lazy check
    if "!lazycheck!" == "1" (
        call :checkwapper continue 0
        if "!continue!" == "0" exit /b
    )

    @REM restore plugins
    call :updateplugins
) else (
    :: cancel
    exit /b
)

@REM wait 3 seconds
timeout /t 3 /nobreak >nul 2>nul

@REM recheck
call :checkconnect available 0
if "!available!" == "1" (
    @echo [%ESC%[95minfo%ESC%[0m] issues has been %ESC%[95mfixed%ESC%[0m and now the network proxy can be used %ESC%[95mnormally%ESC%[0m
) else (
    @echo [%ESC%[91merror%ESC%[0m] issues repair %ESC%[91mfailed%ESC%[0m, the network proxy is still %ESC%[91munavailable%ESC%[0m, please try other methods
)
goto :eof


@REM check if the network is available
:checkwapper <result> <enable>
set "%~1=1"
call :trim loglevel "%~2"
if "!loglevel!" == "" set "loglevel=1"

call :isavailable available 0 "https://www.baidu.com" ""
if "!available!" == "0" (
    @echo [%ESC%[91merror%ESC%[0m] your network is %ESC%[91munavailable%ESC%[0m, but proxy program is %ESC%[91mnot running%ESC%[0m. please check the network first

    @REM should terminate
    set "%~1=0"
    exit /b
)

if "!loglevel!" == "1" (
    @echo [%ESC%[97mwarning%ESC%[0m] network proxy is %ESC%[91mnot running%ESC%[0m, recommend you choose %ESC%[97mRestart%ESC%[0m to execute it
)
goto :eof


@REM update workflow
:updateplugins
if "!quickflag!" == "1" goto :quickupdate

@REM run as admin
if "!asdaemon!" == "1" (
    cacls "%SystemDrive%\System Volume Information" >nul 2>&1 || (start "" mshta vbscript:CreateObject^("Shell.Application"^).ShellExecute^("%~snx0"," %*","","runas",!show!^)^(window.close^)&exit /b)
)

@REM prepare all plugins
call :prepare changed 1

@REM no new version found
if "!changed!" == "0" (
    @echo [%ESC%[95minfo%ESC%[0m] don't need update due to not found new version
) else (
    @REM wait for overwrite files
    timeout /t 3 /nobreak >nul 2>nul
)

@REM postclean
call :cleanworkspace "!temp!"

@REM startup
call :startclash
goto :eof


@REM parse and validate arguments
:argsparse
set result=false

if "%1" == "-a" set result=true
if "%1" == "--alpha" set result=true
if "!result!" == "true" (
    set "alpha=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-c" set result=true
if "%1" == "--conf" set result=true
if "!result!" == "true" (
    @REM validate argument
    call :trim subscription "%~2"

    if "!subscription!" == "" set result=false
    if "!subscription:~0,2!" == "--" set result=false
    if "!subscription:~0,1!" == "-" set result=false

    if "!result!" == "false" (
        @echo [%ESC%[91merror%ESC%[0m] invalid argument, must provide a %ESC%[91mvalid%ESC%[0m %ESC%[97mconfiguration file%ESC%[0m or %ESC%[97msubscription link%ESC%[0m if you specify "%ESC%[97m--conf%ESC%[0m"
        @echo.
        goto :usage
    )

    if "!subscription:~0,8!" == "https://" set "isweblink=1"
    if "!subscription:~0,7!" == "http://" set "isweblink=1"
    if "!isweblink!" == "1" (
        set "invalid=0"

        @REM include '"' see https://stackoverflow.com/questions/46238709/how-to-detect-if-input-is-quote
        @echo !subscription! | findstr /i /r /c:"\"^" >nul && (set "invalid=1")

        @REM contain whitespace
        if "!subscription!" neq "!subscription: =!" set "invalid=1"
        @REM match url
        echo "!subscription!" | findstr /i /r /c:^"\"http.*://.*[a-zA-Z0-9][a-zA-Z0-9]*\"^" >nul 2>nul || (set "invalid=1")

        if "!invalid!" == "1" (
            set "shouldexit=1"

            @echo [%ESC%[91merror%ESC%[0m] invalid subscription link "%ESC%[97m!subscription!%ESC%[0m"
            @echo.
            goto :eof
        ) 
        set "sublink=!subscription!"
    ) else (
        set "invalid=1"
        if "!subscription:~-5!" == ".yaml" (set "invalid=0") else (
            if "!subscription:~-4!" == ".yml" (set "invalid=0")
        )
        if "!invalid!" == "0" (
            set "configuration=!subscription!"
        ) else (
            set "shouldexit=1"

            @echo [%ESC%[91merror%ESC%[0m] invalid configuration "%ESC%[97m!subscription!%ESC%[0m", only "%ESC%[97m.yaml%ESC%[0m" and "%ESC%[97m.yml%ESC%[0m" files are supported
            @echo.
            goto :eof
        )
    )
    shift & shift & goto :argsparse
)

if "%1" == "-d" set result=true
if "%1" == "--daemon" set result=true
if "!result!" == "true" (
    set "asdaemon=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-e" set result=true
if "%1" == "--exclude" set result=true
if "!result!" == "true" (
    set "exclude=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-f" set result=true
if "%1" == "--fix" set result=true
if "!result!" == "true" (
    set "repair=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-h" set result=true
if "%1" == "--help" set result=true
if "!result!" == "true" (
    call :usage
)

if "%1" == "-i" set result=true
if "%1" == "--init" set result=true
if "!result!" == "true" (
    set "initflag=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-k" set result=true
if "%1" == "--kill" set result=true
if "!result!" == "true" (
    set "killflag=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-m" set result=true
if "%1" == "--meta" set result=true
if "!result!" == "true" (
    set "clashmeta=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-o" set result=true
if "%1" == "--overload" set result=true
if "!result!" == "true" (
    set "reloadonly=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-p" set result=true
if "%1" == "--purge" set result=true
if "!result!" == "true" (
    set "purgeflag=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-q" set result=true
if "%1" == "--quick" set result=true
if "!result!" == "true" (
    set "quickflag=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-r" set result=true
if "%1" == "--restart" set result=true
if "!result!" == "true" (
    set "restartflag=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-s" set result=true
if "%1" == "--show" set result=true
if "!result!" == "true" (
    set "show=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-t" set result=true
if "%1" == "--test" set result=true
if "!result!" == "true" (
    set "testflag=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-u" set result=true
if "%1" == "--update" set result=true
if "!result!" == "true" (
    set "updateflag=1"
    set result=false
    shift & goto :argsparse
)

if "%1" == "-w" set result=true
if "%1" == "--workspace" set result=true
if "!result!" == "true" (
    @REM validate argument
    call :trim param "%~2"
    if "!param!" == "" set result=false
    if "!param:~0,2!" == "--" set result=false
    if "!param:~0,1!" == "-" set result=false

    if "!result!" == "false" (
        @echo [%ESC%[91merror%ESC%[0m] invalid argument, if you set "%ESC%[97m--workspace%ESC%[0m" you must specify an path
        @echo.
        goto :usage
    )

    call :pathconvert directory "!param!"
    if not exist "!directory!" (
        call :makedirs success "!directory!"
        if "!success!" == "1" (rd "!directory!" /s /q >nul 2>nul) else (set "shouldexit=1")
    )

    if "!shouldexit!" == "1" (
        @echo [%ESC%[91merror%ESC%[0m] the specified path "%ESC%[97m!directory!%ESC%[0m" for "%ESC%[97m--workspace%ESC%[0m" is %ESC%[91minvalid%ESC%[0m
        @echo.
        goto :eof
    )

    set "dest=!directory!"
    set result=false
    shift & shift & goto :argsparse
)

if "%1" == "-y" set result=true
if "%1" == "--yacd" set result=true
if "!result!" == "true" (
    set "yacd=1"
    set result=false
    shift & goto :argsparse
)

@REM will throw exception if this code not in here or delete it or merge with <if "%1" NEQ "">. why?
if "%1" == "" goto :eof

if "%1" NEQ "" (
    call :trim syntax "%~1"
    if "!syntax!" == "goto" (
        call :trim funcname "%~2"
        if "!funcname!" == "" (
            @echo [%ESC%[91merror%ESC%[0m] invalid syntax, function name cannot by empty when use goto
            goto :usage
        )

        for /f "tokens=1-2,* delims= " %%a in ("%*") do set "params=%%c"
        if "!params!" == "" (
            call !funcname!
            exit /b
        ) else (
            call !funcname! !params!
            exit /b
        )
    )

    @echo [%ESC%[91merror%ESC%[0m] arguments error, unknown: %ESC%[91m%1%ESC%[0m
    @echo.
    goto :usage
)

goto :eof


@REM help
:usage
@echo Usage: !batname! [OPTIONS]
@echo.
@echo arguments: support long options and short options
@echo -a, --alpha          alpha version allowed for clash, the stable version is used by default, use with %ESC%[97m-i%ESC%[0m or %ESC%[97m-u%ESC%[0m
@echo -c, --conf           specify a configuration file, support local files and subscription links
@echo -d, --daemon         run on background as daemon, default is false
@echo -e, --exclude        skip subscriptions when updating
@echo -f, --fix            %ESC%[91moverwrite%ESC%[0m all plugins to fix network issues
@echo -h, --help           display this help and exit
@echo -i, --init           initialize network proxy with the configuration provided by %ESC%[97m-c%ESC%[0m
@echo -k, --kill           close network proxy by kill clash process
@echo -m, --meta           if configuration is compatible, use clash.meta instead of clash premium, use with %ESC%[97m-i%ESC%[0m or %ESC%[97m-u%ESC%[0m
@echo -o, --overload       only reload configuration files
@echo -p, --purge          turn off system network proxy, disable booting and automatic updating
@echo -q, --quick          quick updates, only subscriptions and rulesets are refreshed
@echo -r, --restart        kill and restart clash process
@echo -s, --show           show running window, hide by default
@echo -t, --test           check whether the network proxy is available
@echo -u, --update         perform update operations on plugins, subscriptions, and rulesets
@echo -w, --workspace      the %ESC%[97mabsolute path%ESC%[0m of clash workspace, default is the path where the current script is located
@echo -y, --yacd           use yacd to replace the standard dashboard, use with %ESC%[97m-i%ESC%[0m or %ESC%[97m-u%ESC%[0m

set "shouldexit=1"
goto :eof


@REM confirm download url and filename according parameters
:versioned <geosite>
set "%~1=0"
set "content="

for /f "tokens=*" %%i in ('findstr /i /r "GEOSITE,.*" "!configfile!"') do set "content=!content!;%%i"
call :searchrules "!content!"

@REM rulesets include GEOSITE, must be clash.meta
if "!notfound!" == "0" (
    set "clashmeta=1"
    set "%~1=1"
    goto :eof
)

set "content="
for /f "tokens=*" %%i in ('findstr /i /r "SCRIPT,.*" "!configfile!"') do set "content=!content!;%%i"
call :searchrules "!content!"

@REM rulesets include SCRIPT, must be clash.premium
if "!notfound!" == "0" (
    set "clashmeta=0"
)
goto :eof


@REM quickly update subscriptions and rulesets
:quickupdate
@REM subscriptions
if "!exclude!" == "0" call :updatesubs 1

@REM rulesets
call :updaterules 1

@REM reload
if "!changed!" == "1" (goto :reload) else (goto :eof)


@REM check if special rules are included
:searchrules
set "rulesets=%~1"
set "notfound=1"

for /F "tokens=1* delims=;" %%f in ("!rulesets!") do (
    :: set "rule=%%f"
    call :trim rule "%%f"
    if /i "!rule:~0,1!"=="-" (
        set "notfound=0"
        goto :eof
    )

    if "%%g" NEQ "" call :searchrules "%%g"
)
goto :eof


@REM update subscriptions
:updatesubs <force>
call :trim force "%~1"
if "!force!" == "" set "force=1"

if "!force!" == "1" (
    @echo [%ESC%[95minfo%ESC%[0m] subscriptions are being updated, only those with type "http" will be updated
)

call :filerefresh changed "^\s+health-check:(\s+)?$" "www.gstatic.com" "!force!"
goto :eof


:splitpath <directory> <filename> <filepath>
set "%~1=%~dp3"
set "%~2=%~nx3"

if "!%~1:~-1!" == "\" set "%~1=!%~1:~0,-1!"
goto :eof


@REM to absolute path
:pathconvert <result> <filename>
call :trim filepath %~2
set "%~1="

if "!filepath!" == "" goto :eof

@echo "!filepath!" | findstr ":" >nul 2>nul && (
    set "%~1=!filepath!"
    goto :eof
) || (
    if "!dest!" NEQ "" (set "basedir=!dest!") else (set "basedir=%~dp0")
    if "!basedir:~-1!" == "\" set "basedir=!basedir:~0,-1!"

    set "filepath=!filepath:/=\!"
    if "!filepath:~0,3!" == ".\\" (
        set "%~1=!basedir!\!filepath:~3!"
    ) else if "!filepath:~0,2!" == ".\" (
        set "%~1=!basedir!\!filepath:~2!"
    ) else (
        set "%~1=!basedir!\!filepath!"
    )
)
goto :eof


@REM connectivity
:checkconnect <result> <allowed>
@REM running status
set "%~1=0"
call :trim output "%~2"
if "!output!" == "" set "output=1"

call :isrunning status
if "!status!" == "0" (
    if "!output!" == "1" (
        @echo [%ESC%[97mwarning%ESC%[0m] network proxy is %ESC%[91mnot available%ESC%[0m because clash.exe is %ESC%[91mnot running%ESC%[0m
    )

    goto :eof
)

@REM call :systemproxy server
call :generateproxy server

@REM detect network is available
call :isavailable status !output! "https://www.google.com" "!server!"
set "%~1=!status!"
goto :eof


@REM check network
:isavailable <result> <allowed> <url> <proxyserver>
set "%~1=0"
call :trim output "%~2"
call :trim url "%~3"
call :trim proxyserver "%~4"

if "!output!" == "" set "output=1"
if "!url!" == "" set "url=https://www.google.com"

@REM check
set "statuscode=000"
if "!proxyserver!" == "" (
    for /f %%a in ('curl --retry 3 --retry-max-time 10 -m 5 --connect-timeout 5 -L -s -o nul -w "%%{http_code}" "!url!"') do set "statuscode=%%a"
) else (
    for /f %%a in ('curl -x !proxyserver! --retry 3 --retry-max-time 10 -m 5 --connect-timeout 5 -L -s -o nul -w "%%{http_code}" "!url!"') do set "statuscode=%%a"
)

if "!statuscode!" == "200" (
    set "%~1=1"
    if "!output!" == "1" (
        @echo [%ESC%[95minfo%ESC%[0m] network proxy is not a problem and %ESC%[95mworks fine%ESC%[0m
    )
) else (
    set "%~1=0"
    if "!output!" == "1" (
        call :postprocess

        @echo [%ESC%[97mwarning%ESC%[0m] network proxy is %ESC%[91mnot available%ESC%[0m, you can %ESC%[97mreload%ESC%[0m it with "%ESC%[97m!batname! -o%ESC%[0m" or %ESC%[97mrestart%ESC%[0m it with "%ESC%[97m!batname! -r%ESC%[0m" or "%ESC%[97m!batname! -f%ESC%[0m" to try to %ESC%[97mfix%ESC%[0m the problem
    )
)
goto :eof


@REM query proxy address
:generateproxy <result>
set "%~1="

call :systemproxy server
if "!server!" NEQ "" (
    set "%~1=!server!"
    goto :eof
)

@REM extract from config file
if exist "!configfile!" (
    call :istunenabled enabled
    if "!enabled!" == "1" goto :eof
    call :extractport port
    if "!port!" == "" goto :eof

    choice /t 5 /d y /n /m "[%ESC%[97mwarning%ESC%[0m] found that the system network proxy is %ESC%[91mnot enabled%ESC%[0m, whether to set it? (%ESC%[97mY%ESC%[0m/%ESC%[97mN%ESC%[0m)? "
    if !errorlevel! == 2 goto :eof

    call :enableproxy "127.0.0.1:!port!"
    set "%~1=127.0.0.1:!port!"
    goto :eof
)
goto :eof


@REM create if directory not exists
:makedirs <result> <directory>
set "%~1=0"
call :trim directory "%~2"
if "!directory!" == "" (
    @echo [%ESC%[97mwarning%ESC%[0m] skip mkdir because file path is empty
    goto :eof
)

if not exist "!directory!" (
    mkdir "!directory!" >nul 2>nul
    if "!errorlevel!" == "0" set "%~1=1"
) else (set "%~1=1")
goto :eof


@REM tun enabled
:istunenabled <enabled>
set "%~1=0"
set "text="

@REM not work in batch but works fine in cmd, why?
@REM for /f "tokens=*" %%a in ('findstr /i /r /c:"^tun:[ ]*" "!configfile!"') do set "text=%%a"

for /f "tokens=1* delims=:" %%a in ('findstr /i /r /c:"tun:[ ]*" "!configfile!"') do set "text=%%a"

@REM not required
call :trim text "!text!"
if "!text!" == "tun" set "%~1=1"
goto :eof


@REM wintun
:downloadwintun <changed> <force>
set "%~1=0"

call :trim force "%~2"
if "!force!" == "" set "force=0"

@REM check if required
call :istunenabled enabled
if "!enabled!" == "0" exit /b

@REM exists
if exist "!dest!\wintun.dll" if "!force!" == "0" goto :eof

set "content="
set "wintunurl=https://www.wintun.net"

for /f delims^=^"^ tokens^=2 %%a in ('curl --retry 5 --retry-max-time 60 --connect-timeout 15 -s -L "!wintunurl!" ^| findstr /i /r "builds/wintun-.*.zip"') do set "content=%%a"
call :trim content !content!

if "!content!" == "" (
    @echo [%ESC%[97mwarning%ESC%[0m] cannot extract wintun download link
    goto :eof
)

set "wintunurl=!wintunurl!/!content!"
@echo [%ESC%[95minfo%ESC%[0m] begin to download wintun for overwrite wintun.dll, link: "!wintunurl!"
curl.exe --retry 5 --retry-max-time 60 --connect-timeout 15 -s -L -C - -o "!temp!\wintun.zip" "!wintunurl!"
if exist "!temp!\wintun.zip" (
    @REM unzip
    tar -xzf "!temp!\wintun.zip" -C !temp!

    @REM clean workspace
    del /f /q "!temp!\wintun.zip" >nul 2>nul

    set "wintunfile=!temp!\wintun\bin\amd64\wintun.dll"
    if exist "!wintunfile!" (
        @REM compare and update
        call :md5compare diff "!wintunfile!" "!dest!\wintun.dll"
        if "!diff!" == "1" (
            set "%~1=1"
            @echo [%ESC%[95minfo%ESC%[0m] new version found, filename: %ESC%[97mwintun.dll%ESC%[0m
            
            @REM delete if exist
            del /f /q "!dest!\wintun.dll" >nul 2>nul
            move "!wintunfile!" "!dest!" >nul 2>nul
        )
    ) else (
        @echo [%ESC%[97mwarning%ESC%[0m] not found wintun.dll, there may be an error downloading
    )
) else (
    @echo [%ESC%[97mwarning%ESC%[0m] wintun download failed, please check link is correct
)
goto :eof


@REM download binary file and data
:donwloadfiles <filenames> <outenable>
set "%~1="
call :trim outenable "%~2"
if "!outenable!" == "" set "outenable=1"
if "!outenable!" == "1" (
    @echo [%ESC%[95minfo%ESC%[0m] downloading clash.exe, domain site and IP address data
)

set "dfiles="

@REM download clash
if "!clashurl!" NEQ "" (
    curl.exe --retry 5 --retry-max-time 120 --connect-timeout 30 -s -L -C - -o "!temp!\clash.zip" "!clashurl!"

    if exist "!temp!\clash.zip" (
        @REM unzip
        tar -xzf "!temp!\clash.zip" -C !temp!

        @REM clean workspace
        del /f /q "!temp!\clash.zip"
    ) else (
        @echo [%ESC%[91merror%ESC%[0m] clash download failed, link: "!clashurl!"
    )

    if exist "!temp!\!clashexe!" (
        @REM rename file
        ren "!temp!\!clashexe!" clash.exe

        set "dfiles=clash.exe"
    ) else (
        @echo [%ESC%[91merror%ESC%[0m] not found "!temp!\!clashexe!", download link: "!clashurl!"
    )
)

@REM download Country.mmdb
if "!countryurl!" NEQ "" (
    curl.exe --retry 5 --retry-max-time 120 --connect-timeout 30 -s -L -C - -o "!temp!\!countryfile!" "!countryurl!"
    if exist "!temp!\!countryfile!" (
        if "!dfiles!" == "" (
            set "dfiles=!countryfile!"
        ) else (
            set "dfiles=!dfiles!;!countryfile!"
        )
    ) else (
        @echo [%ESC%[91merror%ESC%[0m] not found "!temp!\!countryfile!", download link: "!countryurl!"
    )
)

@REM download GeoSite.dat
if "!geositeurl!" NEQ "" (
    curl.exe --retry 5 --retry-max-time 120 --connect-timeout 30 -s -L -C - -o "!temp!\!geositefile!" "!geositeurl!"

    if exist "!temp!\!geositefile!" (
        if "!dfiles!" == "" (
            set "dfiles=!geositefile!"
        ) else (
            set "dfiles=!dfiles!;!geositefile!"
        )
    ) else (
        @echo [%ESC%[91merror%ESC%[0m] "!temp!\!geositefile!" not exists, download link: "!geositeurl!"
    )
)

@REM download GeoIP.dat
if "!geoipurl!" NEQ "" (
    curl.exe --retry 5 --retry-max-time 120 --connect-timeout 30 -s -L -C - -o "!temp!\!geoipfile!" "!geoipurl!"

    if exist "!temp!\!geoipfile!" (
        if "!dfiles!" == "" (
            set "dfiles=!geoipfile!"
        ) else (
            set "dfiles=!dfiles!;!geoipfile!"
        )
    ) else (
        @echo [%ESC%[91merror%ESC%[0m] cannot found file "!temp!\!geoipfile!", download link: "!geoipurl!"
    )
)

set "%~1=!dfiles!"
goto :eof


@REM compare
:detect <result> <filenames>
set "%~1=0"
set "filenames=%~2"

for %%a in (!filenames!) do (
    set "fname=%%a"

    if not exist "!temp!\!fname!" (
        @echo [%ESC%[91merror%ESC%[0m] %ESC%[97m!fname!%ESC%[0m download finished, but not found it in directory "!temp!"
        goto :eof
    )

    if "!repair!" == "1" (
        @REM delete for triggering upgrade
        del /f /q "!dest!\!fname!" >nul 2>nul
    )

    @REM found new file
    if not exist "!dest!\!fname!" (
        set "%~1=1"
        call :upgrade "!filenames!"
        exit /b
    )

    @REM compare and update
    call :md5compare diff "!temp!\!fname!" "!dest!\!fname!"
    if "!diff!" == "1" (
        set "%~1=1"
        @echo [%ESC%[95minfo%ESC%[0m] new version found, filename: %ESC%[97m!fname!%ESC%[0m
        call :upgrade "!filenames!"
        exit /b
    )
)
goto :eof


@REM compare file with md5
:md5compare <changed> <source> <target>
set "%~1=0"

call :trim source "%~2"
call :trim target "%~3"

if not exist "!source!" if not exist "!target!" goto :eof
if not exist "!source!" goto :eof
if not exist "!target!" (
    set "%~1=1"
    goto :eof
)

@REM source md5
set "original=" & for /F "skip=1 delims=" %%h in ('2^> nul CertUtil -hashfile "!source!" MD5') do if not defined original set "original=%%h"
@REM target md5
set "received=" & for /F "skip=1 delims=" %%h in ('2^> nul CertUtil -hashfile "!target!" MD5') do if not defined received set "received=%%h"

if "!original!" NEQ "!received!" (set "%~1=1")
goto :eof


@REM update clash.exe and data
:upgrade <filenames>
call :trim filenames "%~1"
if "!filenames!" == "" goto :eof

@REM make sure the file exists
set "existfiles="
for %%a in (!filenames!) do (
    if exist "!temp!\%%a" (
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
call :killprocesswrapper

@REM copy file
for %%a in (!filenames!) do (
    set "fname=%%a"

    @REM delete if old file exists
    if exist "!dest!\!fname!" (
        del /f /q "!dest!\!fname!" >nul 2>nul
    )
    
    @REM move new file to dest
    move "!temp!\!fname!" "!dest!" >nul 2>nul
)
goto :eof


@REM start
:startclash
call :isrunning status

if "!status!" == "0" (
    @REM startup clash
    call :executewrapper 0
) else (
    @echo [%ESC%[95minfo%ESC%[0m] subscriptions and rulesets have been updated, and the reload operation is about to be performed
    goto :reload
)
goto :eof


@REM privilege escalation
:privilege <args> <show>
set "hidewindow=0"
set "operation=%~1"
if "!operation!" == "" (
    @echo [%ESC%[91merror%ESC%[0m] invalid operation, mus support function name
    exit /b 1
)

@REM parse window parameter
call :trim param "%~2"
set "display=" & for /f "delims=0123456789" %%i in ("!param!") do set "display=%%i"
if defined display (set "hidewindow=0") else (set "hidewindow=!param!")
if "!hidewindow!" NEQ "0" set "hidewindow=1"

cacls "%SystemDrive%\System Volume Information" >nul 2>&1 && (!operation!) || (start "" mshta vbscript:CreateObject^("Shell.Application"^).ShellExecute^("%~snx0","%~1","","runas",!hidewindow!^)^(window.close^)&exit /b)
goto :eof


@REM execute
:execute <config>
call :trim cfile "%~1"

if "!cfile!" == "" (
    @echo [%ESC%[95minfo%ESC%[0m] cannot execute clash.exe, invalid config path
    goto :eof
)

@REM privilege escalation
call :nopromptrunas success

@REM execute
call :splitpath filepath filename "!cfile!" 
"!filepath!\clash.exe" -d "!filepath!" -f "!cfile!"
goto :eof


@REM ensure all plugins exist
:prepare <changed> <force>
set "%~1=0"

call :trim downforce "%~2"
if "!downforce!" == "" set "downforce=0"

@REM dashboard directory name
call :extractpath dashboard

@REM confirm download url and filename
call :versioned geositeneed

@REM confirm donwload url
call :confirmurl "!downforce!" "!geositeneed!"

@REM precleann workspace
call :cleanworkspace "!temp!"

@REM update dashboard
call :dashboardupdate "!downforce!"

@REM update subscriptions
if "!exclude!" == "0" call :updatesubs "!downforce!"

@REM update rulefiles
call :updaterules "!downforce!"

@REM wintun.dll
call :downloadwintun newwintun "!downforce!"
set "%~1=!newwintun!"

@REM download clah.exe and geoip.data and so on
call :donwloadfiles filenames "!downforce!"

@REM judge file changed with md5
call :detect changed "!filenames!"
if "!changed!" == "1" set "%~1=!changed!"

goto :eof


@REM config autostart and auto update
:postprocess
call :privilege "goto :nopromptrunas" 0

@REM tips
call :outputhint

@REM allow auto start when user login
call :autostart

@REM allow auto check update
call :autoupdate
goto :eof


@REM privilege escalation
:executewrapper <shouldcheck>
call :trim shouldcheck "%~1"
if "!shouldcheck!" == "" set "shouldcheck=0"
if "!shouldcheck!" == "1" (call :prepare changed 0)

@REM verify config
if not exist "!dest!\clash.exe" (
    @echo [%ESC%[91merror%ESC%[0m] %ESC%[91mfailed%ESC%[0m to start clash.exe, program "%ESC%[97m!dest!\clash.exe%ESC%[0m" is missing
    goto :eof
)

if not exist "!configfile!" (
    @echo [%ESC%[91merror%ESC%[0m] %ESC%[91mfailed%ESC%[0m to start clash.exe, not found configuration file "%ESC%[97m!configfile!%ESC%[0m"
    goto :eof
)

set "testoutput=!temp!\clashtestout.txt"
del /f /q "!testoutput!" >nul 2>nul

@REM test config file
"!dest!\clash.exe" -d "!dest!" -t "!configfile!" > "!testoutput!"

@REM failed
if !errorlevel! NEQ 0 (
    set "messages="
    if exist "!testoutput!" (
        for /f "tokens=1* delims==" %%a in ('findstr /i /r /c:"[ ]ERR[ ]\[config\][ ].*" "!testoutput!"') do set "messages=%%b"
        del /f /q "!testoutput!" >nul 2>nul
    )

    if "!messages!" == "" set "messages=unknown error"
    @echo [%ESC%[91merror%ESC%[0m] clash.exe %ESC%[91mfailed%ESC%[0m to start because of some errors in the configuration file "%ESC%[97m!configfile!%ESC%[0m"
    @echo [%ESC%[91merror%ESC%[0m] messages: "!messages!"
    exit /b 1
)

@REM delete test output
del /f /q "!testoutput!" >nul 2>nul

@REM run clash.exe with config
call :privilege "goto :execute !configfile!" !show!

@REM waiting
timeout /t 5 /nobreak >nul 2>nul

@REM check running status
call :isrunning status

if "!status!" == "1" (
    @echo [%ESC%[95minfo%ESC%[0m] execute clash.exe %ESC%[95msuccess%ESC%[0m, network proxy is %ESC%[95menabled%ESC%[0m

    @REM auto start 
    call :postprocess
) else (
    @echo [%ESC%[91merror%ESC%[0m] execute clash.exe %ESC%[91mfailed%ESC%[0m, please check if the %ESC%[91mconfiguration%ESC%[0m is correct
)
goto :eof


@REM search port on config file with keyword
:searchport <result> <key>
set "%~1="
set "content="
call :trim key "%~2"
if "!key!" == "" goto :eof

@REM search
for /f "tokens=1* delims=:" %%a in ('findstr /i /r /c:"^^!key!:[ ][ ]*[0-9][0-9]*" "!configfile!"') do set "content=%%b"
if "!content!" == "" goto :eof

call :trim port "!content!"
if "!port!" NEQ "" set "%~1=!port!"
goto :eof


@REM extract proxy port
:extractport <result>
set "%~1=7890"
set "keys=mixed-port;port;socks-port"
for %%a in (!keys!) do (
    call :searchport port "%%a"
    if "!port!" NEQ "" (
        set "%~1=!port!"
        exit /b
    )
)
goto :eof


@REM print warning if tun is disabled
:outputhint
call :istunenabled enabled
if "!enabled!" == "1" goto :eof

call :extractport proxyport
if "!proxyport!" == "" set "proxyport=7890"

@REM set proxy
set "proxyserver=127.0.0.1:!proxyport!"
call :systemproxy server
if "!proxyserver!" NEQ "!server!" (
    choice /t 5 /d y /n /m "[%ESC%[97mwarning%ESC%[0m] found that the system network proxy is %ESC%[91mnot enabled%ESC%[0m, whether to set it? (%ESC%[97mY%ESC%[0m/%ESC%[97mN%ESC%[0m)? "
    if !errorlevel! == 1 call :enableproxy "!proxyserver!"
)

@REM hint
@echo [%ESC%[97mwarning%ESC%[0m] if you cannot use the network proxy, please go to "%ESC%[97mSettings -^> Network & Internet -^> Proxy%ESC%[0m" to confirm whether the proxy has been set to "%ESC%[97m!proxyserver!%ESC%[0m"
goto :eof


@REM restart program
:restartprogram
@REM check running status
call :isrunning status
if "!status!" == "1" (
    @REM kill process
    call :killprocesswrapper

    @REM check running status
    call :isrunning status

    if "!status!" == "1" (
        @echo [%ESC%[97mwarning%ESC%[0m] restart clash.exe %ESC%[91mfailed%ESC%[0m due to %ESC%[97mcannot stop%ESC%[0m it
        goto :eof
    )
)

@REM if alpha=1 may cause clash download failure
set "alpha=0"

@REM startup
call :executewrapper 1
exit /b


@REM run as admin
:killprocesswrapper
call :isrunning status
if "!status!" == "0" goto :eof

@echo [%ESC%[95minfo%ESC%[0m] kill clash process with administrator permission
call :privilege "goto :killprocess" 0

@REM wait a moment
timeout /t 6 /nobreak >nul 2>nul

@REM detect
call :isrunning status
if "!status!" == "0" (
    @echo [%ESC%[95minfo%ESC%[0m] network proxy program has exited %ESC%[95msuccessfully%ESC%[0m. if you want to restart it you can execute with "%ESC%[97m!batname! -r%ESC%[0m"

    @REM disable proxy
    @REM call :istunenabled enabled
    @REM if "!enabled!" == "0" call :disableproxy

    call :disableproxy
) else (
    @echo [%ESC%[97mwarning%ESC%[0m] kill network proxy process %ESC%[91mfailed%ESC%[0m, you can close it manually in %ESC%[97mtask manager%ESC%[0m
)
goto :eof


@REM stop
:killprocess
tasklist | findstr /i "clash.exe" >nul 2>nul && taskkill /im "clash.exe" /f >nul 2>nul
set "exitcode=!errorlevel!"

@REM no prompt
call :nopromptrunas success

@REM waiting for release
timeout /t 2 /nobreak >nul 2>nul

@REM detect running status
call :isrunning status

if "!status!" == "0" (
    @echo [%ESC%[95minfo%ESC%[0m] clash.exe process exits successfully, and the network proxy is closed
) else (
    @echo [%ESC%[91merror%ESC%[0m] failed to close network proxy, cannot exit clash process, status: !exitcode!
)
goto :eof


@REM delect running status
:isrunning <result>
tasklist | findstr /i "clash.exe" >nul 2>nul && set "%~1=1" || set "%~1=0"
goto :eof


@REM get donwload url
:confirmurl <force> <enabled>
@REM country data
call :trim force "%~1"
if "!force!" == "" set "force=0"

call :trim geositeflag "%~2"
if "!geositeflag!" == "" set "geositeflag=0"

set "needdownload=0"
set "countryurl=https://raw.githubusercontent.com/Hackl0us/GeoIP2-CN/release/Country.mmdb"

@REM geosite/geoip filename
set "countryfile=Country.mmdb"
set "geositefile=GeoSite.dat"
set "geoipfile=GeoIP.dat"

@REM dashboard url
set "dashboardurl=https://github.com/Dreamacro/clash-dashboard/archive/refs/heads/gh-pages.zip"
set "dashdirectory=clash-dashboard-gh-pages"

set "clashurl="

@REM determine whether to download clash.exe
if not exist "!dest!\clash.exe" (set "needdownload=1") else (set "needdownload=!force!")

if "!clashmeta!" == "0" (
    set "clashexe=clash-windows-amd64.exe"

    if "!needdownload!" == "1" (
        if "!alpha!" == "0" (
            for /f "tokens=1* delims=:" %%a in ('curl --retry 5 -s -L "https://api.github.com/repos/Dreamacro/clash/releases/tags/premium" ^| findstr /i /r /c:"https://github.com/Dreamacro/clash/releases/download/premium/clash-windows-amd64-[^v][^3].*.zip"') do set "clashurl=%%b"
            
            @REM remove whitespace
            call :trim clashurl "!clashurl!"
            if !clashurl! == "" (
                @echo [%ESC%[91merror%ESC%[0m] cannot extract download url for clash.premium, version: stable
                goto :eof
            )
            set "clashurl=!clashurl:~1,-1!"
        ) else (
            set "clashurl=https://release.dreamacro.workers.dev/latest/clash-windows-amd64-latest.zip"
        )
    )

    if "!yacd!" == "1" (
        set "dashboardurl=https://github.com/haishanh/yacd/archive/refs/heads/gh-pages.zip"
        set "dashdirectory=yacd-gh-pages"
    )
) else (
    set "clashexe=Clash.Meta-windows-amd64.exe"
    set "geositeurl=https://raw.githubusercontent.com/Loyalsoldier/domain-list-custom/release/geosite.dat"
    set "geoipurl=https://raw.githubusercontent.com/Loyalsoldier/geoip/release/geoip-only-cn-private.dat"

    if "!needdownload!" == "1" (
        if "!alpha!" == "1" (
            for /f "tokens=1* delims=:" %%a in ('curl --retry 5 -s -L "https://api.github.com/repos/MetaCubeX/Clash.Meta/releases?prerelease=true&per_page=10" ^| findstr /i /r "https://github.com/MetaCubeX/Clash.Meta/releases/download/Prerelease-Alpha/Clash.Meta-windows-amd64-alpha-.*.zip"') do set "clashurl=%%b"
        ) else (
            for /f "tokens=1* delims=:" %%a in ('curl --retry 5 -s -L "https://api.github.com/repos/MetaCubeX/Clash.Meta/releases/latest?per_page=1" ^| findstr /i /r "https://github.com/MetaCubeX/Clash.Meta/releases/download/.*/Clash.Meta-windows-amd64-.*.zip"') do set "clashurl=%%b"
        )

        call :trim clashurl "!clashurl!"
        if !clashurl! == "" (
            @echo [%ESC%[91merror%ESC%[0m] cannot extract download url for clash.meta
            goto :eof
        )

        set "clashurl=!clashurl:~1,-1!"
    )

    @REM geosite.data download url
    if "!geositeflag!" == "0" (
        set "geositeurl="
    ) else (
        for /f "tokens=1* delims=:" %%a in ('findstr /i /r /c:"^[ ][ ]*geosite:[ ][ ]*" "!configfile!"') do (
            call :trim geositekey %%a

            @REM commented
            if /i "!geositekey:~0,1!" NEQ "#" call :trim geositeurl %%b
        )
    )

    @REM geodata-mode
    set "geodatamode=false"
    for /f "tokens=1,2 delims=:" %%a in ('findstr /i /r /c:"^geodata-mode:[ ][ ]*" "!configfile!"') do (
        call :trim gmn %%a

        @REM commented
        if /i "!gmn:~0,1!" NEQ "#" call :trim geodatamode %%b
    )

    @REM geoip.data
    if "!geodatamode!" == "false" (
        set "geoipurl="

        for /f "tokens=1* delims=:" %%a in ('findstr /i /r /c:"^[ ][ ]*mmdb:[ ][ ]*" "!configfile!"') do (
            call :trim mmdbkey %%a

            @REM commented
            if /i "!mmdbkey:~0,1!" NEQ "#" call :trim countryurl %%b
        )
    ) else (
        set "countryurl="

        for /f "tokens=1* delims=:" %%a in ('findstr /i /r /c:"^[ ][ ]*geoip:[ ][ ]*http.*://" "!configfile!"') do (
            call :trim geoipkey %%a
            
            @REM commented
            if /i "!geoipkey:~0,1!" NEQ "#" call :trim geoipurl %%b
        )
    )

    if "!yacd!" == "1" (
        set "dashboardurl=https://github.com/MetaCubeX/Yacd-meta/archive/refs/heads/gh-pages.zip"
        set "dashdirectory=Yacd-meta-gh-pages"
    )
)

@REM clashurl
call :generateurl clashurl "!clashurl!" "clash.exe" "!force!"

@REM dashboardurl
if "!dashboard!" == "" (
    @REM don't need dashboard
    set "dashboardurl="
) else (
    set "needdash=!force!"
    if not exist "!dashboard!\index.html" set "needdash=1"
    if "!needdash!" == "0" (
        set "dashboardurl="
    ) else (
        call :ghproxywrapper dashboardurl !dashboardurl!
    )
)

@REM countryurl
call :generateurl countryurl "!countryurl!" "!countryfile!" "!force!"

@REM geositeurl
call :generateurl geositeurl "!geositeurl!" "!geositefile!" "!force!"

@REM geoipurl
call :generateurl geoipurl "!geoipurl!" "!geoipfile!" "!force!"
goto :eof


@REM generate real download url
:generateurl <result> <url> <filename> <force>
set "%~1="

call :trim url "%~2"
if "!url!" == "" goto :eof

call :trim filename "%~3"
if "!filename!" == "" goto :eof

if not exist "!dest!\!filename!" (set "needdownload=1") else (set "needdownload=!force!")
if "!needdownload!" == "0" goto :eof

call :ghproxywrapper downloadurl !url!

set "%~1=!downloadurl!"
goto :eof


@REM leading and trailing whitespace
:trim <result> <rawtext>
set "rawtext=%~2"
set "%~1="
if "!rawtext!" == "" goto :eof

for /f "tokens=* delims= " %%a in ("!rawtext!") do set "rawtext=%%a"

@REM for /l %%a in (1,1,100) do if "!rawtext:~-1!"==" " set "rawtext=!rawtext:~0,-1!"

@REM for speed, iteration set to 10
for /l %%a in (1,1,10) do if "!rawtext:~-1!"==" " set "rawtext=!rawtext:~0,-1!"

set "%~1=!rawtext!"
goto :eof


@REM wrapper github
:ghproxywrapper <result> <rawurl>
set "%~1="
call :trim rawurl %~2
if "!rawurl!" == "" goto :eof

@REM github proxy
set "ghproxy=https://ghproxy.com"

if "!rawurl:~0,18!" == "https://github.com" set "rawurl=!ghproxy!/!rawurl!"
if "!rawurl:~0,33!" == "https://raw.githubusercontent.com" set "rawurl=!ghproxy!/!rawurl!"
if "!rawurl:~0,34!" == "https://gist.githubusercontent.com" set "rawurl=!ghproxy!/!rawurl!"

set "%~1=!rawurl!"
goto :eof


@REM search keywords with powershell
:findby <filepath> <regex> <resultfile>
call :trim filepath %~1
if "!filepath!" == "" goto :eof

set "regex=%~2"
if "!regex!" == "" goto :eof

call :trim result %~3
if "!result!" == "" goto :eof

powershell -command "& {&'Get-Content' '!filepath!' | &'Select-String' -Pattern '!regex!' -Context 5,5 | &'Set-Content' -Encoding 'utf8' '!result!'}";
goto :eof


@REM remove leading and trailing quotes
:removequotes <result> <str>
set "%~1="
call :trim str "%~2"
if "!str!" == "" goto :eof

if !str:~0^,1!!str:~-1! equ "" set "str=!str:~1,-1!"
if "!str:~0,1!!str:~0,1!" == "''" set "str=!str:~1!"
if "!str:~-1!!str:~-1!" == "''" set "str=!str:~0,-1!"
set "%~1=!str!"
goto :eof


@REM query value from yaml
:parsevalue <result> <regex>
set "%~1="
set "regex=%~2"
if "!regex!" == "" goto :eof

set "key="
set "text="
for /f "tokens=1* delims=:" %%a in ('findstr /i /r /c:"!regex!" "!configfile!"') do (
    set "key=%%a"
    set "text=%%b"
)

call :trim key "!key!"
if "!key!" == "" goto :eof
@REM commened 
if "!key:~0,1!" == "#" goto :eof

call :removequotes value "!text!"
set "%~1=!value!"
goto :eof


@REM reload config
:reload
if not exist "!configfile!" goto :eof

@REM clash api address
call :parsevalue clashapi "external-controller:[ ][ ]*"
if "!clashapi!" == "" (
    @echo [%ESC%[91merror%ESC%[0m] %ESC%[91mdon't%ESC%[0m support reload, maybe you can use "%ESC%[97m!batname! -r%ESC%[0m" to restart or configure "%ESC%[97mexternal-controller%ESC%[0m" in file "%ESC%[97m!configfile!%ESC%[0m" to enable this operation
    goto :eof
)
set "clashapi=http://!clashapi!/configs?force=true"

@REM secret
call :parsevalue secret "secret:[ ][ ]*"

@REM running detect
call :isrunning status

if "!status!" == "1" (
    @REM '\' to '\\'
    set "filepath=!configfile:\=\\!"

    @REM call api for reload
    set "statuscode=000"
    set "output=!temp!\clashout.txt"
    if exist "!output!" del /f /q "!output!" >nul 2>nul

    if "!secret!" NEQ "" (
        for /f %%a in ('curl --retry 3 -L -s -o "!output!" -w "%%{http_code}" -H "Content-Type: application/json" -H "Authorization: Bearer !secret!" -X PUT -d "{""path"":""!filepath!""}" "!clashapi!"') do set "statuscode=%%a"
    ) else (
        for /f %%a in ('curl --retry 3 -L -s -o "!output!" -w "%%{http_code}" -H "Content-Type: application/json" -X PUT -d "{""path"":""!filepath!""}" "!clashapi!"') do set "statuscode=%%a"
    )

    if "!statuscode!" == "204" (
        @echo [%ESC%[95minfo%ESC%[0m] proxy program reload %ESC%[95msucceeded%ESC%[0m, wish you a happy use
        call :postprocess
    ) else if "!statuscode!" == "401" (
        @echo [%ESC%[95minfo%ESC%[0m] %ESC%[97msecret%ESC%[0m has been %ESC%[91mmodified%ESC%[0m, please use "%ESC%[97m!batname! -r%ESC%[0m" to restart
    ) else (
        set "content="

        if exist "!output!" (
            @REM read output
            for /f "delims=" %%a in (!output!) do set "content=%%a"
        )

        @echo [%ESC%[91merror%ESC%[0m] reload %ESC%[91mfailed%ESC%[0m, please check if your configuration file is valid and try again
        if "!content!" NEQ "" (
            @echo [%ESC%[91merror%ESC%[0m] error message: "!content!"
        )

        @echo.
    )

    @REM delete
    del /f /q "!output!" >nul 2>nul
) else (
    @echo [%ESC%[91merror%ESC%[0m] clash.exe is %ESC%[91mnot running%ESC%[0m, skip reload. you can start it with command "%ESC%[97m!batname! -r%ESC%[0m"
)
goto :eof


@REM update rules
:updaterules <force>
call :trim force "%~1"
if "!force!" == "" set "force=1"

if "!force!" == "1" (
    @echo [%ESC%[95minfo%ESC%[0m] checking and updating rulesets of type "http"
)

call :filerefresh changed "^\s+behavior:\s+.*" "www.gstatic.com" "!force!"
goto :eof


@REM refresh subsribe and rulesets
:filerefresh <result> <regex> <filter> <force>
set "%~1=0"
set "regex=%~2"

call :trim filter "%~3"
if "!filter!" == "" set "filter=www.gstatic.com"

call :trim force "%~4"
if "!force!" == "" set "force=1"

if "!regex!" == "" (
    @echo [%ESC%[97mwarning%ESC%[0m] skip update, keywords cannot empty
    goto :eof
)

set texturls=
set localfiles=

if not exist "!configfile!" goto :eof

@REM temp file
set "tempfile=!temp!\clashupdate.txt"

call :findby "!configfile!" "!regex!" "!tempfile!"
if not exist "!tempfile!" (
    if "!force!" == "0" goto :eof

    @echo [%ESC%[97mwarning%ESC%[0m] ignore download file due to cannot extract config from file "!configfile!"
    goto :eof
)

@REM urls and file path
for /f "tokens=1* delims=:" %%i in ('findstr /i /r /c:"^[ ][ ]*url:[ ][ ]*http.*://.*" !tempfile!') do (
    @echo "%%j" | findstr "!filter!" >nul 2>nul || set "texturls=!texturls!,%%j"
)

for /f "tokens=1* delims=:" %%i in ('findstr /i /r /c:"^[ ][ ]*path:[ ][ ]*.*" !tempfile!') do set "localfiles=!localfiles!,%%j"

for %%u in (!texturls!) do (
    call :trim url %%u
    for /f "tokens=1* delims=," %%r in ("!localfiles!") do (
        if /i "!url:~0,8!"=="https://" (
            @REM ghproxy
            call :ghproxywrapper url !url!

            @REM generate file path
            call :pathconvert tfile %%r
            if "!tfile!" == "" (
                @echo [%ESC%[91merror%ESC%[0m] refresh error because config is invalid
                goto :eof  
            )

            set "needdownload=0"
            if not exist "!tfile!" set "needdownload=1"
            if "!force!" == "1" set "needdownload=1"
            @REM should download
            if "!needdownload!" == "1" (
                @REM get directory
                call :splitpath filepath filename "!tfile!"
                @REM mkdir if not exists
                call :makedirs success "!filepath!"
                @REM request and save
                curl.exe --retry 5 --retry-max-time 90 -m 120 --connect-timeout 15 -s -L -C - "!url!" > "!temp!\!filename!"
                @REM check file
                set "filesize=0"
                if exist "!temp!\!filename!" (
                    for %%a in ("!temp!\!filename!") do set "filesize=%%~za"
                )

                if !filesize! GTR 16 (
                    @REM delete if old file exists
                    del /f /q "!tfile!" >nul 2>nul
                    @REM move new file to dest
                    move "!temp!\!filename!" "!filepath!" >nul 2>nul
                    @REM changed status 
                    set "%~1=1"
                ) else (
                    @echo [%ESC%[91merror%ESC%[0m] %ESC%[97m!filename!%ESC%[0m download error, link: "!url!"
                )
            )

            set "localfiles=%%s"
        )
    )
)

@REM delete tempfile
if exist "!tempfile!" del /f /q "!tempfile!" >nul 2>nul
goto :eof


@REM extract dashboard path
:extractpath <result>
set "%~1="

if not exist "!configfile!" goto :eof

set "keyname="
set "content="
for /f "tokens=1,* delims=:" %%a in ('findstr /i /r /c:"external-ui:[ ][ ]*" "!configfile!"') do (
    set "keyname=%%a"
    set "content=%%b"
)

@REM not found 'external-ui' configuration in config file
call :trim keyname "!keyname!"
if "!keyname!" NEQ "external-ui" goto :eof

call :trim content "!content!"
if "!content!" == "" goto :eof

call :pathconvert directory "!content!"
set "%~1=!directory!"
goto :eof


@REM upgrade dashboard
:dashboardupdate <force>
call :trim force "%~1"
if "!force!" == "" set "force=0"

if "!dashboardurl!" == "" (
    if "!force!" == "0" goto :eof

    @echo [%ESC%[95minfo%ESC%[0m] %ESC%[97mskip%ESC%[0m update dashboard because it's %ESC%[97mnot enabled%ESC%[0m
    goto :eof
)

if "!dashboard!" == "" (
    @echo [%ESC%[91merror%ESC%[0m] parse dashboard directory error, dashboard: "!dashboard!"
    goto :eof
)

@REM exists
if exist "!dashboard!\index.html" if "!force!" == "0" goto :eof

call :makedirs success "!dashboard!"

@echo [%ESC%[95minfo%ESC%[0m] start download and upgrading the dashboard
curl.exe --retry 5 -m 120 --connect-timeout 20 -s -L -C - -o "!temp!\dashboard.zip" "!dashboardurl!"

if not exist "!temp!\dashboard.zip" (
    @echo [%ESC%[97mwarning%ESC%[0m] fail to download dashboard, link: "!dashboardurl!"
    goto :eof
)

@REM unzip
tar -xzf "!temp!\dashboard.zip" -C !temp!
del /f /q "!temp!\dashboard.zip" >nul 2>nul

@REM base path and directory name
call :splitpath dashpath dashname "!dashboard!"
if "!dashpath!" == "" (
    @echo [%ESC%[91merror%ESC%[0m] cannot extract base path for dashboard
    goto :eof
)

if "!dashname!" == "" (
    @echo [%ESC%[91merror%ESC%[0m] cannot extract dashboard directory name
    goto :eof
)

@REM rename
ren "!temp!\!dashdirectory!" !dashname!

@REM replace if dashboard download success
dir /a /s /b "!temp!\!dashname!" | findstr . >nul && (
    call :replacedir "!temp!\!dashname!" "!dashboard!"
    @echo [%ESC%[95minfo%ESC%[0m] dashboard has been updated to the latest version
) || (
    @echo [%ESC%[97mwarning%ESC%[0m] occur error when download dashboard, link: "!dashboardurl!"
)
goto :eof


@REM overwrite files
:replacedir <src> <dest>
set "src=%~1"
set "target=%~2"

if "!src!" == "" (
    @echo [%ESC%[97mwarning%ESC%[0m] skip to replace files because resource path is empty
    goto :eof
)

if "!target!" == "" (
    @echo [%ESC%[97mwarning%ESC%[0m] skip to replace files because destination path is empty
    goto :eof
)

if not exist "!src!" (
    @echo [%ESC%[91merror%ESC%[0m] overwrite files error, directory not exist, resource: "!src!"
    goto :eof  
)

@REM delete old folder if exists
if exist "!target!" rd "!target!" /s /q >nul 2>nul

@REM copy to dest
xcopy "!src!" "!target!" /h /e /y /q /i >nul 2>nul

@REM delete source dashboard
rd "!src!" /s /q >nul 2>nul
goto :eof


@REM delete if file exists
:cleanworkspace
set "directory=%~1"
if "!directory!" == "" set "directory=!temp!"

if exist "!directory!\clash.zip" del /f /q "!directory!\clash.zip" >nul
if exist "!directory!\clash.exe" del /f /q "!directory!\clash.exe" >nul

@REM wintun
if exist "!directory!\wintun.zip" del /f /q "!directory!\wintun.zip" >nul
if exist "!directory!\wintun" rd "!directory!\wintun" /s /q >nul

if "!clashexe!" NEQ "" (
    if exist "!directory!\!clashexe!" del /f /q "!directory!\!clashexe!" >nul
)

if "!countryfile!" NEQ "" (
    if exist "!directory!\!countryfile!" del /f /q "!directory!\!countryfile!" >nul
)

if "!geositefile!" NEQ "" (
    if exist "!directory!\!geositefile!" del /f /q "!directory!\!geositefile!" >nul
)

if "!geoipfile!" NEQ "" (
    if exist "!directory!\!geoipfile!" del /f /q "!directory!\!geoipfile!" >nul
)

@REM delete directory
if "!dashdirectory!" NEQ "" (
    if exist "!directory!\!dashdirectory!" rd "!directory!\!dashdirectory!" /s /q >nul
)

if "!dashboard!" == "" goto :eof
if exist "!directory!\!dashboard!.zip" del /f /q "!directory!\!dashboard!.zip" >nul
if exist "!directory!\!dashboard!" rd "!directory!\!dashboard!" /s /q >nul
goto :eof


@REM replace '\\' to '\' for directory 
:pathregular <result> <directory>
set "%~1="
call :trim directory "%~2"

if "!directory!" == "" goto :eof

@REM '\\' to '\'
set "directory=!directory:\\=\!"

@REM '/' to '\'
set "directory=!directory:/=\!"

@REM remove last '\'
if "!directory:~-1!" == "\" set "directory=!directory:~0,-1!"
set "%~1=!directory!"
goto :eof


@REM define exit function
:terminate
@echo [%ESC%[91merror%ESC%[0m] update failed, file clash.exe Country.mmdb or dashboard missing
call :cleanworkspace "!temp!"
exit /b 1
goto :eof


@REM close
:closeproxy
call :isrunning status
if "!status!" == "0" (
    @echo [%ESC%[95minfo%ESC%[0m] no need to kill because network proxy %ESC%[97mis not running%ESC%[0m
    goto :eof
)

choice /t 6 /d y /n /m "[%ESC%[97mwarning%ESC%[0m] this action will close network proxy, do you want to continue (%ESC%[97mY%ESC%[0m/%ESC%[97mN%ESC%[0m)? "
if !errorlevel! == 2 exit /b 1
goto :killprocesswrapper


@REM output with color
:setESC
for /F "tokens=1,2 delims=#" %%a in ('"prompt #$H#$E# & echo on & for %%b in (1) do rem"') do (
  set ESC=%%b
  exit /b 0
)
exit /b 0


@REM set proxy
:enableproxy <server>
call :trim server "%~1"
if "!server!" == "" goto :eof

reg add "!proxyregpath!" /v ProxyEnable /t REG_DWORD /d 1 /f >nul 2>nul
reg add "!proxyregpath!" /v ProxyServer /t REG_SZ /d "!server!" /f >nul 2>nul
reg add "!proxyregpath!" /v ProxyOverride /t REG_SZ /d "<local>" /f >nul 2>nul
goto :eof


@REM cancel proxy
:disableproxy
reg add "!proxyregpath!" /v ProxyServer /t REG_SZ /d "" /f >nul 2>nul
reg add "!proxyregpath!" /v ProxyEnable /t REG_DWORD /d 0 /f >nul 2>nul
reg add "!proxyregpath!" /v ProxyOverride /t REG_SZ /d "" /f >nul 2>nul
goto :eof


@REM query proxy status
:systemproxy <result>
set "%~1="

@REM enabled
call :regquery enable "!proxyregpath!" "ProxyEnable" "REG_DWORD"
if "!enable!" NEQ "0x1" goto :eof

@REM proxy server
call :regquery server "!proxyregpath!" "ProxyServer" "REG_SZ"
if "!server!" NEQ "" set "%~1=!server!"
goto :eof


@REM auto start when user login
:autostart
call :regquery exename "!autostartregpath!" "Clash" "REG_SZ"
if "!startupvbs!" NEQ "!exename!" (
    choice /t 5 /d y /n /m "[%ESC%[97mwarning%ESC%[0m] whether to add network proxy program to boot automatically (%ESC%[97mY%ESC%[0m/%ESC%[97mN%ESC%[0m)? "
    if !errorlevel! == 2 exit /b 1

    call :nopromptrunas success
    if "!success!" == "0" (
        @echo [%ESC%[91merror%ESC%[0m] %ESC%[91mfailed%ESC%[0m to obtain permission, unable to join boot autostart
        goto :eof
    )

    call :generatestartvbs "!startupvbs!" "-r"
    call :registerexe success "!startupvbs!"
    if "!success!" == "1" (
        @echo [%ESC%[95minfo%ESC%[0m] network proxy program is automatically started at boot time
    ) else (
        @echo [%ESC%[91merror%ESC%[0m] %ESC%[91mfailed%ESC%[0m to obtain permission, unable to join boot autostart
    )
)
goto :eof


@REM disable auto start
:disableautostart <result>
set "%~1=0"
call :regquery exename "!autostartregpath!" "Clash" "REG_SZ"

if "!exename!" == "" (
    set "%~1=1"
) else (
    set "shoulddelete=1"
    if "!startupvbs!" NEQ "!exename!" (
        choice /t 5 /d n /n /m "[%ESC%[97mwarning%ESC%[0m] found same program but different execution paths, whether to continue (%ESC%[97mY%ESC%[0m/%ESC%[97mN%ESC%[0m)? "
        if !errorlevel! == 2 set "shoulddelete=0"
    )
    if "!shoulddelete!" == "1" (
        reg delete "!autostartregpath!" /v "Clash" /f >nul 2>nul
        if "!errorlevel!" == "0" set "%~1=1"
        
        @REM disable
        reg delete "!startupapproved!" /v "Clash" /f >nul 2>nul
    )
)
goto :eof


@REM add scheduled tasks
:autoupdate <refresh>
call :trim refresh "%~1"
if "!refresh!" == "" set "refresh=0"
set "taskname=ClashUpdater"

call :taskstatus ready "!taskname!"
if "!refresh!" == "1" set "ready=0"

if "!ready!" == "0" (
    choice /t 5 /d y /n /m "[%ESC%[97mwarning%ESC%[0m] whether to allow automatic checking for updates? (%ESC%[97mY%ESC%[0m/%ESC%[97mN%ESC%[0m)? "
    if !errorlevel! == 2 exit /b 1

    set "operation=-u"
    if "!clashmeta!" == "1" set "operation=!operation! -m"
    if "!alpha!" == "1" set "operation=!operation! -a"
    if "!yacd!" == "1" set "operation=!operation! -y"

    call :generatestartvbs "!updatevbs!" "!operation!"
    call :deletetask success "!taskname!"
    call :createtask success "!updatevbs!" "!taskname!"
    if "!success!" == "1" (
        @echo [%ESC%[95minfo%ESC%[0m] automatic update scheduled task is set %ESC%[95msuccessfully%ESC%[0m
    ) else (
        @echo [%ESC%[91merror%ESC%[0m] automatic update scheduled task setting %ESC%[91mfailed%ESC%[0m
    )
)
goto :eof


@REM create scheduled tasks
:createtask <result> <path> <taskname>
set "%~1=0"
call :trim exename "%~2"
if "!exename!" == "" goto :eof

call :trim taskname "%~3"
if "!taskname!" == "" goto :eof

@REM create
schtasks /create /tn "!taskname!" /tr "!exename!" /sc daily /mo 1 /ri 360 /st 09:30 /du 0012:00 /f >nul 2>nul
if "!errorlevel!" == "0" set "%~1=1"
goto :eof


@REM query scheduled tasks
:taskstatus <status> <taskname>
set "%~1=0"
call :trim taskname "%~2"
if "!taskname!" == "" goto :eof

@REM query
schtasks /query /tn "!taskname!" >nul 2>nul
if "!errorlevel!" NEQ "0" goto :eof

set "status="
for /f "usebackq skip=3 tokens=4" %%a in (`schtasks /query /tn "!taskname!"`) do set "status=%%a"
call :trim status "!status!"

if "!status!" == "Ready" set "%~1=1"
goto :eof


@REM delete scheduled tasks
:deletetask <result> <taskname>
set "%~1=0"
call :trim taskname "%~2"
if "!taskname!" == "" goto :eof

schtasks /query /tn "!taskname!" >nul 2>nul
@REM not found
if "!errorlevel!" NEQ "0" (
    set "%~1=1"
    goto :eof
)

schtasks /delete /tn "!taskname!" /f >nul 2>nul
if "!errorlevel!" == "0" set "%~1=1"
goto :eof


@REM add to 
:registerexe <result> <path>
set "%~1=0"
call :trim exename "%~2"
if "!exename!" == "" goto :eof
if not exist "!exename!" goto :eof

@REM delete
reg delete "!autostartregpath!" /v "Clash" /f >nul 2>nul
@REM register
reg add "!autostartregpath!" /v "Clash" /t "REG_SZ" /d "!exename!" >nul 2>nul
if "!errorlevel!" NEQ "0" goto :eof

@REM approved
reg delete "!startupapproved!" /v "Clash" /f >nul 2>nul
@REM register
reg add "!startupapproved!" /v "Clash" /t "REG_BINARY" /d "02 00 00 00 00 00 00 00 00 00 00 00" >nul 2>nul

if "!errorlevel!" == "0" set "%~1=1"
goto :eof


@REM vbs for startup
:generatestartvbs <path> <operation>
call :trim startscript "%~1"
if "!startscript!" == "" goto :eof

call :trim operation "%~2"
if "!operation!" == "" goto :eof

@echo set ws = WScript.CreateObject^("WScript.Shell"^) > "!startscript!"
@echo ws.Run "%~dp0!batname! !operation! -w !dest! -c !configfile!", 0 >> "!startscript!"
@echo set ws = Nothing >> "!startscript!"
goto :eof


@REM judge os caption
:ishomeedition <result>
set "%~1=1"

set "content=" 
for /f %%a in ('wmic os get OperatingSystemSKU ^| findstr /r /i /c:"^[1-9][0-9]*"') do set "content=%%a"
call :trim content "!content!"

@REM 2/3/5/26 represent home edition
if "!content!" NEQ "2" if "!content!" NEQ "3" if "!content!" NEQ "5" if "!content!" NEQ "26" (
    for /f "delims=" %%a in ('wmic os get caption ^| findstr /i /c:"pro" /c:"professional"') do set "content=%%a"
    call :trim content "!content!"
    if "!content!" NEQ "" set "%~1=0"
)
goto :eof


@REM enable run as admin
:enablerunas <result>
set "%~1=1"

call :ishomeedition edition
if "!edition!" == "0" goto :eof

set "packagesfile=!temp!\grouppolicypackages.txt"

@REM find all grouppolicy pakcages
dir /b "C:\Windows\servicing\Packages\Microsoft-Windows-GroupPolicy-ClientExtensions-Package~3*.mum" > "!packagesfile!"
dir /b "C:\Windows\servicing\Packages\Microsoft-Windows-GroupPolicy-ClientTools-Package~3*.mum" >> "!packagesfile!"

@REM install
for /f %%i in ('findstr /i . "!packagesfile!" 2^>nul') do dism /online /norestart /add-package:"C:\Windows\servicing\Packages\%%i" >nul 2>nul
if "!errorlevel!" NEQ "0" set "%~1=0"

del /f /q "!packagesfile!" >nul 2>nul
goto :eof


@REM no prompt when run as admin
:nopromptrunas <result>
set "%~1=0"

call :enablerunas enable
if "!enable!" == "0" goto :eof

@REM no prompt
set "grouppolicy=HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
set "gprkey=ConsentPromptBehaviorAdmin"

call :regquery code "!grouppolicy!" "!gprkey!" "REG_DWORD"
if "!code!" NEQ "0x0" (
    reg delete "!grouppolicy!" /v ConsentPromptBehaviorAdmin /f >nul 2>nul
    reg add "!grouppolicy!" /v ConsentPromptBehaviorAdmin /t REG_DWORD /d 0 /f >nul 2>nul
    if "!errorlevel!" == "0" set "%~1=1"
    goto :eof
)

set "%~1=1"
goto :eof


@REM clean data
:purge
choice /t 6 /d n /n /m "[%ESC%[97mwarning%ESC%[0m] %ESC%[97msystem network proxy%ESC%[0m will be closed and the %ESC%[97mboot autostart%ESC%[0m is disabled, do you want to continue? (%ESC%[97mY%ESC%[0m/%ESC%[97mN%ESC%[0m)? "
if !errorlevel! == 2 exit /b 1

@REM get administrator privileges
call :privilege "goto :nopromptrunas" 0

@REM wait
timeout /t 5 /nobreak >nul 2>nul

@REM close system proxy
call :disableproxy

@REM disable auto start
call :disableautostart success
if "!success!" == "0" (
    @echo [%ESC%[91merror%ESC%[0m] disable auto start %ESC%[91mfailed%ESC%[0m, please delete it manually
)

@REM delete scheduled
call :deletetask success "ClashUpdater"
if "!success!" == "0" (
    @echo [%ESC%[91merror%ESC%[0m] delete automatic check for updates task %ESC%[91mfailed%ESC%[0m, please delete it manually in %ESC%[97mtask scheduler%ESC%[0m 
)

@REM stop process
call :killprocesswrapper

@echo [%ESC%[95minfo%ESC%[0m] cleaned up %ESC%[95msuccessfully%ESC%[0m, bye~
goto :eof


@REM query value form register
:regquery <result> <path> <key> <type>
set "%~1="
set "value="

@REM path
call :trim rpath "%~2"
if "!rpath!" == "" goto :eof

@REM key
call :trim rkey "%~3"
if "!rkey!" == "" goto :eof

@REM type
call :trim rtype "%~4"
if "!rtype!" == "" set "rtype=REG_SZ"

@REM query
reg query "!rpath!" /V "!rkey!" >nul 2>nul
if "!errorlevel!" NEQ "0" goto :eof

for /f "tokens=3" %%a in ('reg query "!rpath!" /V "!rkey!" ^| findstr /r /i "!rtype!"') do set "value=%%a"
call :trim value "!value!"
set "%~1=!value!"
goto :eof


endlocal