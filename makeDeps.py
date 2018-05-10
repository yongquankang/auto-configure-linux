# 10209416 10/02/2017 initial version, parsing configure dependencies
#		The Kconfig semantics are complicated, more rules to be
#		added if necessary


import os,sys,re
import subprocess

def usage():
	print '%s:<kernelPath> <config_item> <config_value>' % sys.argv[0]
	print "<config_value> to be 'y/n' to select/dis-select, or string to set value, Eg:NR_CPUS 24"
	sys.exit(1)

if len(sys.argv) != 3:
	usage()

kernelPath = sys.argv[1]
os.environ["KERNEL_SOURCE"] = kernelPath
config_item = sys.argv[2]
config_value = sys.argv[3]
config_item = re.compile('^CONFIG_').sub('', config_item)
if not config_item:
	print 'The format of item is incorrect: [CONFIG_]UPPER_CASE_ITEM'
	sys.exit(1)

if not os.path.exists(kernelPath):
	print 'Please make sure the given parameters:'
	print '\tkernel path:%s' % kernelPath
	print is correct'
	sys.exit(1)

# shell script which calls expect
SHELL_EXP_SCRIPT = r"""
exp_config()
{
    if [[ -z $ITEM || -z $VAL || -z $KERNEL_SOURCE ]];then
        echo "The environment variables: ITEM,VAL,KERNEL_SOURCE,ARCH are not set correctly"
        return 1
    fi

expect << 'EOF'
set item $env(ITEM)
set config_value $env(VAL)
spawn make -C $env(KERNEL_SOURCE) config

set timeout 30
match_max 5000
set expect_out(buffer) {}
set choiceOpt ""
set matched 0
set send_human {.1 .3 1 .05 2}

expect {
        # begin with *+[0-9.]+(key)
        # "  4. Preemptible Kernel (Basic RT) (PREEMPT_RTB)"
        -re ".*(\[1-9])\\..*\\($item\\).*" {
                set buff $expect_out(buffer)
                set choiceOpt $expect_out(1,string)
                set matched 1
                set choiceStr ""
                regexp ".*(choice\\\[.*\\\]:).*" $buff all choiceStr
                if {$choiceStr != ""} {
                        exp_send -h "$choiceOpt\r"
                }
                exp_continue
        }
        # choice option
        -re {.*choice\[.*\]:} {
                if {$matched == 1} {
                        exp_send -h "$choiceOpt\r"
                } else {
                        exp_send "\r"
                }
                set matched 0
                exp_continue
        }
        # with +(key)+[option]
        # "PowerEN PCIe Chroma Card (PPC_CHROMA) [N/y]"
        -regexp {.*\(([0-9A-Za-z_]+)\)\s+\[.*} {
        # weird. The rule here may missing some keyStrs, to be investigated
                set keyStr $expect_out(1,string)
                if {$keyStr == $item} {
            exp_send -h "$config_value\r"
                } else {
                        exp_send -h "\r"
                }
                exp_continue
        }
        # selection without brackets
        # eg. USB Gadget Drivers [M/y/?] (there's no item in ())
        -regexp {.*\s+\[.*} {
                exp_send "\r"
                exp_continue
        }
        # More regular rules to be investigated
        "configuration written to .config" {
                send_user "the configuration completed!\n"
                exp_send "\r"
                interact
        }
        timeout {
                exit 1
        }
        eof {
                exit
        }
}
EOF
}
exp_config
"""

def findSubstring(fullstr,substr,times):
	current=0
	for i in range(1, times+1):
		current=fullstr.find(substr,current)+1
		if current == 0:
			return -1
	return current-1

def boolOfString(depString):
    if not depString or '<choice>' == depString:
        return True
    depString = depString.replace('&&', ' && ').replace('||', ' || ').replace('(',' ( ').replace(')', ' ) ')
    depString = ' ' + depString
    str=re.compile('([&|()])').sub(' ', depString).strip()
    l=re.compile('\s+').split(str)
    for i in l:
        if not i:
            return True
        if 'true' == i.strip() or 'false' == i.strip():
            continue
        i = ' ' + i

        if '!' == i.strip()[0]:
            if '=n' in i:
                depString = depString.replace(i, 'true')
            else:
                depString = depString.replace(i, 'false')
        else:
            if '=n' in i:
                depString = depString.replace(i, 'false')
            else:
                depString = depString.replace(i, 'true')

    depString = depString.replace('&&', ' && ').replace('||', ' || ').replace('(',' ( ').replace(')', ' ) ')
    if '||' in depString:
        for i in range(1, len(depString)):
            finOr = findSubstring(depString, '||', i)
            if finOr == -1:
                i = i - 1
                finOr = findSubstring(depString, '||', i)
                break
        firOr = findSubstring(depString, '||', 1)
        sl = list(depString)
        sl.insert(len(depString), ' ) ')
        sl.insert(firOr+2, ' ( ')
        depString = "".join(sl)
        if i > 1:
            for x in range(2, i+1):
                ret = findSubstring(depString, '||', x)
                sl = list(depString)
                sl.insert(ret, ')')
                sl.insert(ret+3, '(')
                depString = "".join(sl)
    return True if os.system(depString) == 0 else False

def menuconfig_item(item, key):
    os.environ["CONF_ITEM"] = item
    os.environ["TERM"] = 'vt100'
    os.environ["TERMINFO"] = '/usr/share/terminfo'
    os.environ["COLUMNS"] = '800'
    os.environ["LINES"] = '80'

    MENUCONFIG_SCRIPT = r"""
expect << 'EOF'
spawn make -C $env(KERNEL_SOURCE) menuconfig
set sp_pid [exp_pid -i $spawn_id]

set timeout 10
match_max 5000
set expect_out(buffer) {}
set myfile [open outputs w+]

expect {
        "Arrow keys navigate the menu.*" {
                exp_send "/"
                exp_continue
        }
        "Search Configuration Parameter" {
                exp_send "$env(CONF_ITEM)\n"
                exp_continue
        }

        -re {.*\(\s*([0-9]+)%\)*} {
                set buff $expect_out(buffer)
                puts $myfile $buff
                set per $expect_out(1,string)
                exp_send "\003"
        }
        timeout {
        exec kill -9 $sp_pid
                exit
        }
}
close $myfile
exec kill -9 $sp_pid
EOF
"""
    p = subprocess.Popen(MENUCONFIG_SCRIPT, shell=True, stdout=None)
    p.wait()

    ret = None
    if key == 'value':
        ret = os.popen("sed '/Symbol: /!d;s/^.*Symbol: //g;s/.*$//g' outputs | sed -n '1p' | sed 's/ \[//g;s/]//g;s/.*=//g'").read().strip()
    elif key == 'depends':
        ret = os.popen("sed '/Symbol: .*%s[_A-Z]/,$d;/Depends on: /!d;s/^.*Depends on: //g;s/.*$//g' outputs | \
							sed -n '1p' | sed 's/ \[//g;s/]//g'" % item).read().strip()
    elif key == 'selected':
        ret = os.popen("sed '/Symbol: .*%s[_A-Z]/,$d;/Selected by: /!d;s/^.*Selected by: //g;s/.*$//g' outputs | \
							sed -n '1p' | sed 's/ \[//g;s/]//g'" % item).read().strip()
    elif key == 'type':
        ret = os.popen("sed '/Symbol: .*%s[_A-Z]/,$d;/Type.*: /!d;s/^.*Type.*: //g;s/.*$//g' outputs | \
							sed -n '1p' | sed 's/ \[//g;s/]//g'" % item).read().strip()
    os.remove('outputs')
    return ret

def validate_config(item, val):
    if 'n' == val and 0 == os.system('grep "^CONFIG_%s=" %s -q' % (item, defconfig)):
            return False
    elif 'y' == val or 'm' == 'val':
        if 0 != os.system('grep "^CONFIG_%s=%s" %s -q' % (item, val, defconfig)):
            return False
    elif type(val) is int:
        itype = menuconfig_item(item, 'type')
        if 'integer' == itype:
            if 0 != os.system('grep "^CONFIG_%s=%s %s -q' % (item, val, defconfig)):
                return False
        if 'hex' == itype:
            if 0 != os.system('grep "^CONFIG_%s=%s %s -q' % (item, hex(val), defconfig)):
                return False
    else:
        if 0 != os.system("grep '^CONFIG_%s=\"%s\"' %s -q" % (item, val, defconfig)):
            return False
    return True

def make_config(item, val):
    os.environ["ITEM"] = item
    os.environ["VAL"] = val
    p = subprocess.Popen(SHELL_EXP_SCRIPT, shell=True, stdout=None)
    p.wait()

def write_config(item, val):
    if validate_config(item, val):
        return True
    if 0 == os.system('grep -Eq "^CONFIG_%s=.*$|^# CONFIG_%s is not set$" %s' % (item, item, defconfig)):
        if '!' == item[0]:
            os.system("sed -i 's/^CONFIG_%s=.*$/# CONFIG_%s is not set/' %s" % (item[1:], item[1:], defconfig))
        else:
            if 'y' == val or 'm' == val:
                os.system("sed -i 's/^CONFIG_%s=.*$/CONFIG_%s=%s/' %s" % (item, item, val, defconfig))
                os.system("sed -i 's/# CONFIG_%s is not set$/CONFIG_%s=%s/' %s" % (item, item, val, defconfig))
            elif type(val) is int:
                itype = menuconfig_item(item, 'type')
                if 'integer' == itype:
                    os.system("sed -i 's/^CONFIG_%s=.*$/CONFIG_%s=%s/' %s" % (item, item, val, defconfig))
                    os.system("sed -i 's/# CONFIG_%s is not set$/CONFIG_%s=%s/' %s" % (item, item, val, defconfig))
                elif 'hex' == itype:
                    os.system("sed -i 's/^CONFIG_%s=.*$/CONFIG_%s=%s/' %s" % (item, item, hex(val), defconfig))
                    os.system("sed -i 's/# CONFIG_%s is not set$/CONFIG_%s=%s/' %s" % (item, item, hex(val), defconfig))
            else:
                    os.system("sed -i 's/^CONFIG_%s=.*$/CONFIG_%s=\"%s\"/' %s" % (item, item, val, defconfig))
                    os.system("sed -i 's/# CONFIG_%s is not set$/CONFIG_%s=\"%s\"/' %s" % (item, item, val, defconfig))
        make_config('AFAKEITEM', 'n') # this is a fake item, aims to update .config
        if validate_config(item, val):
            return True
    make_config(item, val)
    return validate_config(item, val)

def do_config(item, val):
    if write_config(item, val):
        return
    deps = menuconfig_item(item, 'depends')
    selected = menuconfig_item(item, 'selected')
    
    if ' m ' in deps:
        if val != 'm' or val != 'n':
            print 'The item:%s is limited to module (=m) or disabled (=n)'
            return
    if selected:
        deps = deps + ' && ' + '( ' + selected + ' )'
    deps = deps.replace('&&', ' && ').replace('||', ' || ').replace('(',' ( ').replace(')', ' ) ')
    if not boolOfString(deps):
        for i in re.compile('\s+').split(deps):
            if not boolOfString(i):
                do_config(i.split('=')[0], 'y')
    if write_config(item, val):
        return
    else:
        print "do_config %s:%s failed" % (item, val)

do_config(config_item,config_value)
