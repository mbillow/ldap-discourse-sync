from csh import cshldap
import requests
import urllib
import cred


class SyncUsers:
    def __init__(self, discourse_group_number, discourse_group_name, ldap_group=None):
        self.ldap = cshldap.LDAP(cred.LDAPUSER, cred.LDAPPASS, app=True)
        self.headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
        self.discourse_group_number = discourse_group_number
        self.discourse_group_name = discourse_group_name
        if not ldap_group:
            ldap_group = discourse_group_name
        self.ldap_group = self.ldap.group(ldap_group)

        login_url = 'https://discourse.csh.rit.edu/auth/ldap/callback'

        values = {'username': cred.USERNAME,
                  'password': cred.PASSWORD}

        data = urllib.urlencode(values)
        r = requests.post(login_url, data, verify=False)
        self.cookies = r.cookies

        self.user_dict = self.group_cycle()

    def group_cycle(self):
        groups_url = 'https://discourse.csh.rit.edu/groups/{}/members.json?limit=2000&offset=0'
        user_dict = {}
        for group_name in ['trust_level_2', 'trust_level_4']:
            users = requests.get(groups_url.format(group_name), cookies=self.cookies, verify=False)
            for entry in users.json()["members"]:
                user_dict[entry["username"]] = entry["id"], group_name
        return user_dict

    def group_list(self, group):
        groups_url = 'https://discourse.csh.rit.edu/groups/{}/members.json?limit=2000&offset=0'
        users = requests.get(groups_url.format(group), cookies=self.cookies, verify=False)
        group_dict = {}
        for entry in users.json()["members"]:
            group_dict[entry["username"]] = entry["id"]
        return group_dict

    def group_update(self):
        group_list_ldap = []
        group_list_discourse = []

        for dn, eboard_member in self.ldap_group:
            group_list_ldap.append(eboard_member['uid'][0])

        for username, id in self.group_list(self.discourse_group_name).iteritems():
            group_list_discourse.append(username)

        not_in_discourse = list(set(group_list_ldap) - set(group_list_discourse))
        not_eboard = list(set(group_list_discourse) - set(group_list_ldap))

        if len(not_in_discourse):
            self.create_member(not_in_discourse)

        # Remove old Eboard members
        for past_eboard_member in not_eboard:
            self.delete_member(past_eboard_member)

    def delete_member(self, username):
        member_id = self.user_dict[username][0]
        values = {'user_id': member_id}
        data = urllib.urlencode(values)
        requests.delete(
            'https://discourse.csh.rit.edu/groups/{number}/members.json{api}'.format(number=self.discourse_group_number,
                                                                                     api=cred.API_INFO),
            headers=self.headers,
            data=data,
            cookies=self.cookies,
            verify=False)
        trust_values = {'user_id': member_id,
                        'level': 2}
        trust_data = urllib.urlencode(trust_values)
        requests.put(
            'https://discourse.csh.rit.edu/admin/users/{id_num}/trust_level{api}'.format(id_num=member_id,
                                                                                         api=cred.API_INFO),
            trust_data, verify=False, headers=self.headers)
        if self.discourse_group_name == 'eboard':
            # Revoke User Moderation Privs
            requests.put(
                    'https://discourse.csh.rit.edu/admin/users/{id}/revoke_moderation{api}'.format(id=member_id,
                                                                                                   api=cred.API_INFO),
                    headers=self.headers, cookies=self.cookies, verify=False)

    def create_member(self, user_list):
        create_list_str = ""
        for new_member in user_list:
            create_list_str += '{},'.format(new_member)
        values = {'usernames': create_list_str[:-1]}
        data = urllib.urlencode(values)

        requests.put(
            'https://discourse.csh.rit.edu/groups/{number}/members.json{api}'.format(number=self.discourse_group_number,
                                                                                     api=cred.API_INFO),
            headers=self.headers,
            data=data,
            cookies=self.cookies,
            verify=False
        )
        if self.discourse_group_name == 'eboard':
            # Grant User Moderation Privs
            for new_member in user_list:
                member_id = self.user_dict[new_member][0]
                r = requests.put(
                    'https://discourse.csh.rit.edu/admin/users/{id}/grant_moderation{api}'.format(id=member_id,
                                                                                                  api=cred.API_INFO),
                    headers=self.headers, cookies=self.cookies, verify=False)

    def sync_birthdays(self):
        request_url = "https://discourse.csh.rit.edu/users/{user}{api}"
        for username in self.user_dict:
            try:

                date = self.ldap.member(username)['birthday'][0]
                birthday = '-'.join([date[:4], date[4:6], date[6:]])[:10]
                if birthday != "":
                    data = {"custom_fields[date_of_birth]": birthday}
                    r = requests.put(request_url.format(user=username, api=cred.API_INFO),
                                     data=data, headers=self.headers, cookies=self.cookies, verify=False)
            except KeyError:
                pass
            except TypeError:
                pass

if __name__ == "__main__":
    SyncUsers('41', 'eboard').group_update()
    SyncUsers('42', 'rtp').group_update()
    SyncUsers('43', 'drink').group_update()
    SyncUsers('44', 'intromembers').group_update()
    SyncUsers('45', 'webmasters', 'webmaster').group_update()
    sync = SyncUsers()
    sync.sync_birthdays()
