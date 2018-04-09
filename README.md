# simple_router_runbook
Built upon NetMiko, this is a simple Python script to execute runbooks against Routers and Switches in a Lab Environment.

The idea is to separate the commands to be executed into a YAML file, instead of containing them within a netmiko python script.

The runbook syntax is intentionally basic.

Currently only tested against Nokia SROS equipment.

Currently only tested on Python 2.7.

## Example of Use

Given a "hosts.yml" file containing hosts and jumphosts with NetMiko parameters, for example:
```
vsim1:
    username: admin
    password: password
    ip: 192.168.1.1 
    device_type: alcatel_sros
    jumphost: jumphost1
7750sr1:
    username: admin
    password: password2
    ip: 192.168.1.2
    device_type: alcatel_sros
    global_delay_factor: 1
jumphost1:
    username: root
    password: password3
    ip: 192.168.1.3
    device_type: terminal_server
    global_delay_factor: 1
    ssh_command: ssh {username}@{ip}
    timeout: 90
    session_timeout: 600
```

And a runbook file containing procedural commands, for example:
```
- LogToFile: health_check_{year}_{month}_{day}_{hour}_{minute}_{second}.txt
- ConnectTo: vsim1
- Exec:
  - show time
- Print: Checking Inventory on {hostname} at {year}/{month}/{day} {hour}:{minute}:{second}
- Exec:
  - show card
  - show mda  
- Print: Next, sleep the Runbook for 5 seconds
- Sleep: 5
- Print: Next, pause script until enter is pressed
- Pause: Pausing Script
```

Execute script as follows:
```
c:\simple_router_runbook> python simple_router_runbook.py example_runbook.yml
logging to: health_check_2018_04_05_22_29_26.txt
connecting to: vsim1
executing:
        "show time"
print "Checking Inventory on vsim1 at 2018/04/05 23:10:47"
executing:
        "show card"
        "show mda"
sleeping for: 5 seconds
pause: "Pausing Script"
<<press enter to continue>>
```

The python script logs the output of the runbook to the log-file defined within the runbook, e.g. "health_check_...txt"
Multiple log-files can used through additional use of "LogToFile" commands within the runbook.
