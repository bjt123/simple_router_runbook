#!/usr/bin/env python
# #############################################################################
# simple_router_runbook.py
#   inputs YML file containing commands for SROS 7450 or equivalent
#   It executes the commands and writes to given log file.
#
#  SVN revision information:
#    @source    $Source:$
#    @author    $Author:$
#    @version   $Revision:$
#    @date      $Date:$
#
# #############################################################################

import sys,re 
import ruamel.yaml
import fnmatch
import os
import subprocess
from netmiko import ConnectHandler
from netmiko import redispatch
import time
import copy
import datetime


# Dictionary Wrapper
class DictionaryWrapper(dict):
   def __init__(self,*arg,**kw):
      super(DictionaryWrapper, self).__init__(*arg, **kw)

# Special function for dealing with sros command side-cases that are not yet merged into the netmiko repo.
def send_sros_command(vars,cmd):
    out_str=""
    if re.match("clear application-assurance group \d+ statistics",cmd):
        vars.nc.write_channel("%s\n" % cmd)
        out_str+=(vars.nc.read_until_pattern('Warning: This may result in statistics inconsistency. Proceed (y/n)?'))
        vars.nc.write_channel("y")
        vars.nc.send_command("")
        out_str+=("\n")
    else:
        out_str+=(vars.nc.send_command(cmd, strip_command=False))
    return out_str # return the commands output without the prompt

# Expand out variables in a string.
# e.g. LogToFile: health_check_{year}_{month}_{day}_{hour}_{minute}_{second}.txt
# Will expand out the current year,month,day...second
# Currently supported variables:
# - hostname: name of currently connected host
# - ip:  IP of currently connected host
# - year, month, day, hour, minute, second:  Current date and time, zero aligned.
def expand_variables(vars,string):
    now=datetime.datetime.now()
    # Create hash array of time attributes, basically a hash containing: year,month,day,hour,minute,second
    array= {method_name : getattr(now,method_name) for method_name in dir(now) if not callable(getattr(now, method_name))}
    # Note: we prepend zeros to certain values, so that minutes of say "1", become "01" ...etc
    for method_name in ['month','day','hour','minute','second']:
       array[method_name]='{:02d}'.format(array[method_name]) 
    # Reference for format spec: https://docs.python.org/2/library/string.html#formatspec
    if hasattr(vars,'connected_to') and vars.connected_to is not None:
        array['hostname']=vars.connected_to['hostname']
        array['ip']=vars.connected_to['ip']
    return string.format(**array) 

# Function to cater for the ambiguous YAML situation where:
# node: value
#   returns "value" as string,
# whereas:
# node:
# - value1
# - value2
#   returns a list.
def yaml_to_list(yml):
    if isinstance(yml, (list, tuple)):
        return yml
    else:
        return [ yml ]

#
# Domain Specific Language commands
#       
def logtofile(vars):
    filename_raw=vars.yml
    filename = expand_variables(vars,filename_raw) 
    sys.stdout.write("logging to: %s\n" % filename)
    vars.out=open(filename,"w")
    if vars.nc is not None:
        vars.out.write("\n%s " % vars.nc.find_prompt())
    return vars

def connectto(vars):
    connect_handler_fields=('device_type', 'ip', 'username', 'password', 'port', 'global_delay_factor', 'timeout', 'session_timeout')
    if vars.yml not in vars.devices:
        raise ValueError("Host not in hostfile: %s" % vars.yml)
    device=vars.devices[vars.yml]
    if "jumphost" in device:
        sys.stdout.write("connecting to jumphost: %s\n" % (device["jumphost"]))
        # copy just the netmiko required arguments into jumphost so to connect to jumphost, unknown keys cause error to ConnectionHandler()
        jumphost={k: vars.devices[device['jumphost']].get(k, None) for k in connect_handler_fields if k in vars.devices[device['jumphost']]}
        ssh_command= vars.devices[device['jumphost']]['ssh_command'].format(**device)
        vars.nc = ConnectHandler(**jumphost)
        vars.nc.find_prompt()
        sys.stdout.write("connecting to: %s\n" % vars.yml)
        vars.nc.write_channel("%s\n" % ssh_command)
        vars.nc.read_until_pattern('assword:')
        sys.stdout.write("sending password\n")
        vars.nc.write_channel('%s\n' % device['password'])
        redispatch(vars.nc, device_type=device['device_type'])
    else:
        host={k: device.get(k, None) for k in connect_handler_fields if k in device} # unknown keys cause errors to ConnectionHandler()
        sys.stdout.write("connecting to: %s\n" % vars.yml)
        vars.nc=ConnectHandler(**host)
    vars.out.write("\n%s " % vars.nc.find_prompt())
    device["hostname"]=vars.yml
    vars.connected_to=device
    return vars

# Execute a router command against the current host
def execute(vars):
    sys.stdout.write("executing:\n")
    for cmd in yaml_to_list(vars.yml):
        sys.stdout.write("\t\"%s\"\n" % cmd)
        if vars.connected_to["device_type"] == 'alcatel_sros':
            vars.out.write(send_sros_command(vars,cmd))
        else:
            raise ValueError('Execute currently only supports: alcatel_sros')
        vars.out.write("\n%s " % (vars.nc.find_prompt())) 
    return vars

# Configure, special function for commands that change the prompt, such as:
#   /configure ...
#   /debug ...
# And also these below, because these also change the prompt:
#   /admin save
#   /bof save
def configure(vars):
    sys.stdout.write("configuring:\n")
    if vars.connected_to["device_type"] != 'alcatel_sros':
        sys.stdout.write("\t CAN ONLY CONFIGURE AN SROS DEVICE!!!\n")
        raise ValueError('Configure currently only supports: alcatel_sros')
    else:
        for cmd in yaml_to_list(vars.yml):
            sys.stdout.write("\t\"%s\"\n" % cmd)
            vars.out.write(vars.nc.send_command(cmd,strip_command=False,expect_string=r'\*?[A-Z]:\S+[#\$]')) # sometimes SROS uses "$" instead of "#" after a "configure...create"
            vars.out.write("\n%s " % (vars.nc.find_prompt())) 
        vars.nc.send_command("exit all",expect_string=r'\*?[A-Z]:\S+[#\$]')
        vars.out.write("\n%s " % (vars.nc.find_prompt())) 
    return vars

# print a string to the current runbook logfile if it exists
def print_to_logfile(vars):
    vars.out.write("\n# \n")
    for line_raw in yaml_to_list(vars.yml):
        line=expand_variables(vars,line_raw)
        sys.stdout.write("print \"%s\"\n" % line)
        vars.out.write("# %s\n" % line)
    if vars.nc is not None:
        vars.out.write("# \n%s " % vars.nc.find_prompt()) 
    return vars

# pause the runbook and wait for prompt
def pause_script(vars):
    vars.out.write("\n# Performing the following: \n")
    for line_raw in yaml_to_list(vars.yml):
        line=expand_variables(vars,line_raw)
        sys.stdout.write("pause: \"%s\"\n" % line)
        vars.out.write("#    %s\n" % line)
    raw_input("<<press enter to continue>>")
    vars.out.write("#\n%s " % vars.nc.find_prompt())
    return vars

# sleep the runbook for a given number of seconds    
def sleep_script(vars):
    vars.out.write("\n#\n")
    for line in yaml_to_list(vars.yml):
        sys.stdout.write("sleeping for: %s seconds\n" % line)
        time.sleep(line)   
        vars.out.write("# Waited for approx.: %s seconds\n" % line)
    vars.out.write("#\n%s " % vars.nc.find_prompt())
    return vars

# function to execute upon unknown runbook command 
def invalid_command(vars):
    print "Invalid Command"
    return vars
    raise ValueError("Invalid Command: %s" % vars)
    
switcher = {
    "LogToFile": logtofile,
    "ConnectTo": connectto,
    "Exec":      execute,
    "Execute":      execute,
    "Configure": configure,
    "Print":     print_to_logfile,
    "Pause":     pause_script,
    "Sleep":     sleep_script,
}
    
def dispatch_function(argument,vars):
    # Get the function from switcher dictionary
    func = switcher.get(argument, invalid_command)
    # Execute the function
    vars=func(vars)
    return vars

# Execute a runbook that is a string
def do_runbook(string):
    yml = ruamel.yaml.load(string, Loader=ruamel.yaml.RoundTripLoader)

    vars=DictionaryWrapper()
    vars.out=sys.stdout
    vars.devices=devices
    vars.nc=None
    vars.snapshot={}
        
    for node in yml:
        key=node.keys()[0];value=node[key]
        vars.yml=value
        vars=dispatch_function(key,vars)
        
    vars.out.close()

#
# MAIN 
# 

devices=None
hostfile="hosts.yml"

if len(sys.argv) < 2: 
    print "USAGE: %s yaml.yml" % sys.argv[0]
    print "  Executes netmiko commands from yaml file"
    print "  Using routers defined in %s" % hostfile

else:
    # load hostfile
    if os.path.isfile(hostfile):
        with open(hostfile, 'r') as myfile:
            string=myfile.read()
            devices = ruamel.yaml.load(string, Loader=ruamel.yaml.RoundTripLoader)
    else:
        raise ValueError("File \"%s\" does not exist" % hostfile)
        
    #loop through every argv runbook
    for arg in (sys.argv[1:]):
        if os.path.isfile(arg):
            with open(arg, 'r') as myfile:
                string=myfile.read()
                do_runbook(string)
        else:
            raise Warning("File \"%s\" does not exist" % arg)
