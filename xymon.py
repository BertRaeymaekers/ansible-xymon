#!/usr/bin/python

ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: xymon
version_added: "1.0"
author: "Bert Raeymaekers (https://github.com/BertRaeymaekers)"
short_description: Controls states of hosts and test in Xymon
description:
- A module to control states of hosts and test in Xymon.
requirements:
- xymon
options:
  xymon_host:
    required: true
    description:
    - "The hostname or IP address of the Xymon server."
  xymon_port:
    required: false
    description:
    - "The port on which the Xymon server is listening."
    default: 1984
  host:
    required: true
    description:
    - "The host as specified in Xymon."
  state:
    required: true
    description:
    - "The desired state."
  test:
    required: false
    description:
    - "The test as specified in Xymon."
    - "It is required for setting a color as state (green, yellow, red) and
       absent."
    - "If not specified (allowed with state disabled or enabled) it will effect
       all the tests on the host."
    default:
  interval:
    required: false
    description:
    - "Required when specifying a colour as state (green, yellow, red) or
       disabled."
    - "It is the time in minutes the status stays valid in xymon. You can
       specify a unit by adding any of these four letter directly after the
       number: s, m, h, d. These are respectively for seconds, minutes, hours
       and days."
    - "Note: for disable Xs doesn't seem to work."
    - "There is one special value: -1 for when setting state disabled, which
      indicates disable until the first green monitoring event cames along."
    default:
  msg:
    required: false
    description:
    - "Xymon message"
    default: "%timestamp% Set %state% by Ansible module xymon."
'''

EXAMPLES = '''
# Disable monitoring for one minute on all test of www.example.com:
- xymon:
    xymon_host: 192.168.0.24
    host: www.example.com
    state: disabled
    interval: 1m

# Disable monitoring for 5 minutes on test httpstatus on www.example.com:
- xymon:
    xymon_host: 192.168.0.24
    host: www.example.com
    test: httpstatus
    state: disabled
    interval: 5

# Enable monitoring for www.example.com:
- xymon:
    xymon_host: 192.168.0.24
    host: www.example.com
    state: enabled

'''

RETURN = '''
'''

STATE_COLOURS = ['green', 'yellow', 'red']
# Removing 'absent' and 'query' until it works
STATE_FIELDS = ('green', 'yellow', 'red', 'disabled', 'enabled')

RETURN_VALUES = '''
{
    "rc": 0
    "msg": "ok"
}
'''


import socket
from time import ctime

from ansible.module_utils.basic import AnsibleModule


class Xymon(object):
    """Communicate with a Xymon server

    server: Hostname or IP address of a Xymon server. Defaults to $XYMSRV
            if set, or 'localhost' if not.
    port:   The port number the server listens on. Defaults to 1984.
    """
    def __init__(self, server=None, port=None):
        if server is None:
            server = os.environ.get('XYMSRV', 'localhost')
        if port is None:
            port=1984
        self.server = server
        self.port = port

    def report(self, host, test, color, message=None, interval=None):
        """Report status to a Xymon server

        host:     The hostname to associate the report with.
        test:     The name of the test or service.
        color:    The color to set. Can be 'green', 'yellow', 'red', or 'clear'
        message:  Details about the current state.
        interval: An optional interval between tests. The status will change
                  to purple if no further reports are sent in this time.
        """
        if not interval:
            interval = '30m'
        if not message:
            message = 'Set %s for %s by Ansible module xymon' % (color, interval)
        args = {
            'host': host,
            'test': test,
            'color': color,
            'message': message,
            'interval': interval,
            'date': ctime(),
        }
        report = '''status+{interval} {host}.{test} {color} {date}
{message}'''.format(**args)
        self.send_message(report)

    def status(self, host, test):
        """Query status to a Xymon server

        host:     The hostname to associate the report with.
        test:     The name of the test or service.
        """
        args = {
            'host': host,
            'test': test,
        }
        report = '''query {host}.{test}'''.format(**args)
        result = self.send_message(report, report=True)
        if result:
            return (result.split()[0], result.split()[1:])
        else:
            return (None, None)

    def enable(self, host, test=None):
        if not test:
            test = "*"
        args = {
            'host': host,
            'test': test
        }
        report = 'enable {host}.{test}'.format(**args)
        self.send_message(report)

    def disable(self, host, interval, test=None, message=None):
        if not test:
            test = "*"
        if not message:
            message = 'Set disabled for %s by Ansible module xymon' % (interval)
        args = {
            'host': host,
            'test': test,
            'interval': interval,
            'message': message,
            'date': ctime(),
        }
        report = 'disable {host}.{test} {interval} {date} {message}'.format(**args)
        self.send_message(report)

    def drop(self, host, test=None):
        if test:
            args = {
                'host': host,
                'test': test
            }
            report = 'drop {host} {test}'.format(**args)
        else:
            args = {
                'host': host
            }
            report = 'drop {host}'.format(**args)
        self.send_message(report)

    def rename(self, host, newhost=None, test=None, newtest=None):
        if newhost:
            if test or newtest:
                raise KeyError("When using newhost, you can't pass test nor newtest")
            args = {
                'oldhost': host,
                'newhost': newhost
            }
            report = 'rename {oldhost} {newhost}'.format(**args)
        elif test and newtest:
            args = {
                'host': host,
                'oldtest': test,
                'newtest': newtest
            }
            report = 'rename {host} {oldtest} {newtest}'.format(**args)
        else:
            raise KeyError("You must eigher pass a newhost or both test and newtest")
        self.sed_message(report)

    def data(self, host, test, raw_data):
        """Report data to a Xymon server

        host:     The hostname to associate the report with.
        test:     The name of the test or service.
        data:     The RRD data.
        """
        args = {
            'host': host,
            'test': test,
            'data': raw_data,
        }
        report = '''data {host}.{test}\n{data}'''.format(**args)
        self.send_message(report)

    def send_message(self, message, report=False):
        """Report arbitrary information to the server

        See the xymon(1) man page for message syntax.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            server_ip = socket.gethostbyname(self.server)
            message = message + '\n'
            s.connect((server_ip, self.port))
            s.sendall(message.encode())
        except:
            # Re-raising the exceptions as this should not pass silently.
            raise
        finally:
            s.close()


def run_module():

    module = AnsibleModule(
        argument_spec = dict(
           xymon_host=dict(required=True, type='str'),
           xymon_port=dict(required=False, type='int'),
           host=dict(required=True, type='str'),
           state=dict(required=True, choices=list(STATE_FIELDS)),
           test=dict(required=False, type='str'),
           interval=dict(required=False, type='str'),
           msg=dict(required=False, type='str')
        ),
        supports_check_mode=False)

    xymon = Xymon(server=module.params['xymon_host'], port=module.params.get('xymon_port', None))

    if module.params['state'] in STATE_COLOURS:
        try:
            xymon.report(
                host=module.params['host'],
                test=module.params['test'],
                color=module.params['state'],
                message=module.params['msg'],
                interval=module.params['interval']
            )
            module.exit_json(changed=True)
        except KeyError:
            module.fail_json(msg="Parameters host, test, msg and interval are required when specifying green, yellow or red.")
        except socket.error as e:
            module.fail_json(msg="Socket error: %s" % (e))
        except Exception as e:
            import traceback
            module.fail_json(msg="%s error: %s" % (type(e), e), traceback=traceback.format_exc())
    elif module.params['state'] == "enabled":
        try:
            xymon.enable(
                host=module.params['host'],
                test=module.params['test']
            )
            module.exit_json(changed=True)
        except KeyError:
            module.fail_json(msg="Parameters host and test are required when specifying state enabled.")
        except socket.error as e:
            module.fail_json(msg="Socket error: %s" % (e))
        except Exception as e:
            import traceback
            module.fail_json(msg="%s error: %s" % (type(e), e), traceback=traceback.format_exc())
    elif module.params['state'] == "disabled":
        try:
            xymon.disable(
                host=module.params['host'],
                test=module.params.get('test', None),
                interval=module.params['interval'],
                message=module.params.get('msg', None)
            )
            module.exit_json(changed=True)
        except KeyError:
            module.fail_json(msg="Parameters host and interval are required when specifying state disabled.")
        except socket.error as e:
            module.fail_json(msg="Socket error: %s" % (e))
        except Exception as e:
            import traceback
            module.fail_json(msg="%s error: %s" % (type(e), e), traceback=traceback.format_exc())
    elif module.params['state'] == "absent":
        try:
            xymon.drop(
                host=module.params['host'],
                test=module.params.get('test', None)
            )
        except KeyError:
            module.fail_json(msg="Parameters host and interval are required when specifying state disabled.")
        except socket.error as e:
            module.fail_json(msg="Socket error: %s" % (e))
        except Exception as e:
            import traceback
            module.fail_json(msg="%s error: %s" % (type(e), e), traceback=traceback.format_exc())
        module.exit_json(changed=True)
    elif module.params['state'] == 'rename':
        try:
            xymon.rename(
                host=module.params['host'],
                test=module.params['test'],
                newhost=module.params['newhost'],
                newest=module.params['newtest']
            )
        except KeyError:
            module.fail_json(msg='Or parameter newhost, or parameter test and newtest must be specified but cannot be mixed when specifying state rename.')
        except socket.error as e:
            module.fail_json(msg="Socket error: %s" % (e))
        except Exception as e:
            import traceback
            module.fail_json(msg="%s error: %s" % (type(e), e), traceback=traceback.format_exc())
        module.exit_json(changed=False)
    elif module.params['state'] == 'query':
        try:
            (status, msg) = xymon.status(
                host=module.params['host'],
                test=module.params['test']
            )
        except KeyError:
            module.fail_json(msg='Parameters host and test are required when querying the state.')
        except socket.error as e:
            module.fail_json(msg="Socket error: %s" % (e))
        except Exception as e:
            import traceback
            module.fail_json(msg="%s error: %s" % (type(e), e), traceback=traceback.format_exc())
        module.exit_json(changed=False, status=status, msg=msg)

def main():
    run_module()

if __name__ == "__main__":
    main()
