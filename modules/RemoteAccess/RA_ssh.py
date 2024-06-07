#!/dls/science/groups/i04/PYTHON3/bin/python3

import paramiko as ssh
import getpass, socket
import pwd as unixpwd
import requests

fedid = getpass.getuser()


class Manage_NX_Connections(object):
    def __init__(self, fedid, hostnames, password):
        self.fedid = fedid
        self.pw = password
        self.nx_machines = hostnames
        # ssh.common.logging.basicConfig(level=ssh.common.DEBUG)
        self.ssh_nx = ssh.SSHClient()
        self.ssh_nx.set_missing_host_key_policy(ssh.AutoAddPolicy())
        self.sessions = [
            [
                "Beamline Machine",
                "NX connection ID",
                "FedID",
                "Name",
                "IP address",
                "City",
                "Country",
                "Remote Hostname",
            ]
        ]

    def get_info_from_ip(self, IP):
        r = requests.get(f"https://ipinfo.io/{IP}")
        return r.json()

    def get_list_of_sessions(self):
        # print(f"username: {self.fedid}")
        for nx_machine in self.nx_machines:
            self.ssh_nx.connect(
                nx_machine,
                username=self.fedid,
                password=self.pw,
                allow_agent=False,
                look_for_keys=False,
            )
            command_check = f"echo '{self.pw}' | sudo -S /usr/NX/bin/nxserver --list"
            stdin, stdout, stderr = self.ssh_nx.exec_command(command_check)
            # print(f'stdin: {stdin}, stdout: {stdout}, stderr:{stderr}')
            stdoutlist = stdout.readlines()
            stderrlist = stderr.readlines()
            # print('STDOUT')
            # print(stdoutlist)
            # print(len(stdoutlist))
            # print(stdoutlist[-3:-1])
            for line in stdoutlist:
                # print(line)
                con_list = line.split()
                # print("###BEFORE INSERT MACHINE JUST RAW SPLIT")
                if len(con_list) == 0:
                    continue
                # print(con_list[0])
                if (
                    con_list
                    != [
                        "-------",
                        "--------",
                        "-------------",
                        "--------------------------------",
                        "--------------",
                    ]
                    and con_list[0] != "NX>"
                    and con_list[0] != "Display"
                    and con_list[0] != "-------"
                    and con_list[0] != "\n"
                ):
                    # Insert OPI
                    con_list.insert(0, nx_machine)
                    # print("After insert machine")
                    # print(con_list)
                    try:
                        if len(con_list) > 2:
                            uni = socket.gethostbyaddr(con_list[3])
                        else:
                            uni = [["No one connected"]]
                    except:
                        uni = ["unknown uni", "unk"]
                    try:
                        if len(con_list) > 2:
                            IPinfo = self.get_info_from_ip(con_list[3])
                            city = IPinfo["city"]
                            country = IPinfo["country"]
                        else:
                            city = "connections empty"
                            country = "connections empty"
                    except:
                        city = "unknown city"
                        country = "unknown country"
                    # Add domain for IP that is connected
                    # print("***Before insert location***")
                    # print(con_list)
                    con_list.insert(4, uni[0])
                    con_list.insert(4, city)
                    con_list.insert(4, country)
                    try:
                        first_name = (
                            unixpwd.getpwuid(unixpwd.getpwnam(con_list[2]).pw_uid)[4]
                            .split(",")[0]
                            .split()[0]
                        )
                        last_name = (
                            unixpwd.getpwuid(unixpwd.getpwnam(con_list[2]).pw_uid)[4]
                            .split(",")[0]
                            .split()[1]
                        )
                    except:
                        # print("### except clause ### ")
                        # print(con_list)
                        if (
                            con_list[2] == "unknown city"
                            or con_list[2] == "unknown country"
                        ):
                            first_name = "unknown"
                        else:
                            try:
                                print(f"Try getpwuid with con_list[2] of {con_list[2]} to get first name")
                                first_name = unixpwd.getpwuid(
                                    unixpwd.getpwnam(con_list[2]).pw_uid
                                )[4]
                            except Exception as e:
                                first_name = ""
                                print(f"Setting empty first name due to error: {e}")
                        last_name = ""
                    name = f"{first_name} {last_name}"
                    # Adding name
                    con_list.insert(3, name)
                    # Remove localhost/port
                    con_list.pop()
                    # Remove session ID
                    con_list.pop()
                    # print(f"con_list is {con_list}")
                    self.sessions.append(con_list)
                    # print(f"current sessions are {self.sessions}")
                # print('STDERR')
                # print(stderrlist)
                self.ssh_nx.close()
        return self.sessions


if __name__ == "__main__":
    pw = getpass.getpass()

    nx_manager = Manage_NX_Connections(fedid, nx_machines, pw)

    connections = nx_manager.get_list_of_sessions()

    from pprint import pprint

    pprint(connections)
