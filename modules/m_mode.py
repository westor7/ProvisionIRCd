#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
/mode command
"""

import ircd

import os
import importlib
import sys
import time
import re

from handle.functions import valid_expire, match, cloak, logging

W  = '\033[0m'  # white (normal)
R  = '\033[31m' # red
G  = '\033[32m' # green
Y  = '\033[33m' # yellow
B  = '\033[34m' # blue
P  = '\033[35m' # purple

### Make these global so they can be modified by modules.
commandQueue = []
modebuf = []
parambuf = []

maxmodes = 24

def makeMask(localServer, data):
    nick, ident, host = '', '', ''
    nick = data.split('!')[0]
    if nick == '' or '@' in nick or ('.' in nick and '@' not in data):
        nick = '*'
    if len(nick) > localServer.nicklen:
        nick = '*{}'.format(nick[-20:])
    try:
        if '@' in data:
            ident = data.split('@')[0]
            if '!' in ident:ident = data.split('@')[0].split('!')[1]
        else:
            ident = data.split('!')[1].split('@')[0]
    except:
        ident = '*'
    if ident == '':
        ident = '*'
    if len(ident) > 12:
        ident = '*{}'.format(ident[-12:])
    try:
        host = data.split('@')[1]
    except:
        if '.' in data:
            try:
                host = ''.join(data.split('@'))
            except:
                host = '*'
    if len(host) > 64:
        host = '*{}'.format(host[-64:])
    if host == '':
        host = '*'
    result = '{}!{}@{}'.format(nick, ident, host)
    return result

oper_override = False
def processModes(self, localServer, channel, recv, sync=True, sourceServer=None, sourceUser=None):
    try:
        if sourceServer != localServer or (type(sourceUser).__name__ == 'User' and sourceUser.server != localServer):
            hook = 'remote_chanmode'
        else:
            hook = 'local_chanmode'
        rawModes = ' '.join(recv[1:])
        if rawModes.startswith(':'):
            rawModes = rawModes[1:]
        if type(sourceUser).__name__ == 'User':
            displaySource = sourceUser.uid
        else:
            displaySource = sourceUser.sid
            if not sourceServer.eos and sourceServer != localServer:
                sync = False
    except Exception as ex:
        logging.exception(ex)
    try:
        chstatus = localServer.chstatus
        global modebuf, parambuf, action, prevaction, commandQueue
        modebuf, parambuf, commandQueue = [], [], []
        action = ''
        prevaction = ''
        paramcount = 0
        chmodes = localServer.chstatus
        ## Setting paramModes
        paramModes = localServer.chstatus
        for x in range(0, 4):
            for m in [m for m in localServer.channel_modes[x] if m not in chmodes]:
                chmodes += m
                if str(x) in '012' and m not in paramModes:
                    paramModes += m
        localServer.parammodes = paramModes
        global oper_override
        local = [e for e in localServer.support if e.split('=')[0] == 'EXTBAN']
        if local:
            extban_prefix = local[0].split('=')[1][0]
        else:
            local = None

        ### Setting some mode level shit.
        ### +v = 1
        ### +h = 2
        ### +o = 3
        ### +a = 4
        ### +q = 5
        ### oper = 6
        ### server = 7
        modeLevel = {
            ### Channel statuses. Users with +h or higher can always remove their own status.
            'v': 2,
            'h': 3,
            'o': 3,
            'a': 4,
            'q': 5
        }
        for t in localServer.channel_modes:
            for m in localServer.channel_modes[t]:
                level = localServer.channel_modes[t][m][0]
                modeLevel[m] = level
        for m in [m for m in recv[1] if m in chmodes+'+-']:
            if m == 'r' and type(self).__name__ != 'Server':
                continue
            if m in '+-' and action != m:
                try:
                    if ''.join(modebuf[-1]) in '+-':
                        del modebuf[-1]
                except:
                    pass
                action = m
                continue
            if not action:
                action = '+'
            if m not in '+-' and action != prevaction and ( (m in chmodes or m in localServer.chstatus) or (action == '-' and m in channel.modes) ):
                modebuf.append(action)
                prevaction = action

            if m not in localServer.chstatus and m not in '+-':
                if self.chlevel(channel) < modeLevel[m] and not self.ocheck('o', 'override'):
                    if m in paramModes:
                       paramcount += 1
                    continue
                elif self.chlevel(channel) < modeLevel[m]:
                    oper_override = True

            if action == '+' and (m in chmodes or type(self).__name__ == 'Server'):
                ###
                ### SETTING CHANNEL MODES
                ###
                if m == 'l' and len(recv) > 2:
                    try:
                        p = recv[2:][paramcount]
                    except IndexError:
                        continue
                    if not p.isdigit():
                        continue
                    if int(p) <= 0:
                        continue
                    if channel.limit == int(p):
                        continue
                    else:
                        if m not in channel.modes:
                            channel.modes += m
                        modebuf.append(m)
                        parambuf.append(p)
                        paramcount += 1
                        channel.limit = int(p)
                        continue

                elif m == 'k' and not channel.key:
                    try:
                        p = recv[2:][paramcount]
                    except Exception as ex:
                        continue
                    if channel.key == p:
                        continue
                    if m not in channel.modes:
                        channel.modes += m
                    modebuf.append(m)
                    parambuf.append(p)
                    paramcount += 1
                    channel.key = p
                    continue

                elif m == 'L' and channel.limit:
                    try:
                        p = recv[2:][paramcount].split(',')[0]
                    except IndexError:
                        continue
                    if p[0] not in localServer.chantypes:
                        continue
                    if channel.redirect == p or p.lower() == channel.name.lower():
                        continue
                    if m not in channel.modes:
                        channel.modes += m
                    modebuf.append(m)
                    parambuf.append(p)
                    paramcount += 1
                    channel.redirect = p
                    continue
                elif m == 'O':
                    if type(self).__name__ != 'Server' and 'o' not in self.modes:
                        continue
                elif m in 'beI':
                    try:
                        rawParam = recv[2:][paramcount]
                    except IndexError:
                        paramcount += 1
                        continue
                    if rawParam.startswith(extban_prefix):
                        paramcount += 1
                        continue
                    mask = makeMask(localServer, rawParam)
                    if m == 'b':
                        data = channel.bans
                        s = 'ban'
                    elif m == 'e':
                        data = channel.excepts
                        s = 'excepts'
                    elif m == 'I':
                        data = channel.invex
                        s = 'invex'
                    if mask not in data:
                        if len(data) >= localServer.maxlist[m] and type(self).__name__ == 'User':
                            self.sendraw(478, '{} {} :Channel {} list is full'.format(channel.name, mask, s))
                            paramcount += 1
                            continue
                        try:
                            setter = self.fullmask()
                        except:
                            setter = self.hostname
                        paramcount += 1
                        modebuf.append(m)
                        parambuf.append(mask)
                        data[mask] = {}
                        data[mask]['setter'] = setter
                        data[mask]['ctime'] = int(time.time())
                        continue

                elif m in chstatus:
                    timed = False
                    # + status
                    try:
                        temp_user = recv[2:][paramcount]
                    except:
                        paramcount += 1
                        continue
                    ### Check to see for timed shit.
                    try:
                        t = recv[2:][paramcount].split(':')
                        temp_user = t[0]
                        ### This is only temporary.
                        try:
                            channel.temp_status
                        except:
                            channel.temp_status = {}
                        if valid_expire(t[1]):
                            timed = valid_expire(t[1])
                    except:
                        pass
                    user = list(filter(lambda u: u.uid == temp_user or u.nickname.lower() == temp_user.lower(), channel.users))
                    if not user:
                        paramcount += 1
                        continue
                    else:
                        user = user[0]
                    if m in channel.usermodes[user]:
                        paramcount += 1
                        continue
                    if type(self).__name__ != 'Server':
                        if self.chlevel(channel) < modeLevel[m] and not self.ocheck('o', 'override'):
                            paramcount += 1
                            continue
                        elif self.chlevel(channel) < modeLevel[m]:
                            oper_override = True

                    channel.usermodes[user] += m
                    modebuf.append(m)
                    parambuf.append(user.nickname)
                    paramcount += 1
                    if timed:
                        channel.temp_status[user] = {}
                        channel.temp_status[user][m] = {}
                        channel.temp_status[user][m]['ctime'] = int(time.time()) + timed
                        channel.temp_status[user][m]['action'] = '-'
                    continue
                # Rest of the modes.
                if m not in channel.modes:
                    if m not in localServer.channel_modes[3]:
                        paramcount += 1
                        continue

                    modebuf.append(m)
                    channel.modes += m
                    if m == 'O' and len(channel.users) > 2:
                        for user in [user for user in channel.users if 'o' not in user.modes]:
                            cmd = ('KICK', '{} {} :Opers only'.format(channel.name, user.nickname))
                            commandQueue.append(cmd)
                    continue

            elif action == '-' and (m in chmodes or type(self).__name__ == 'Server'):
                ###
                ### REMOVING CHANNEL MODES
                ###
                if m in channel.modes:
                    if m == 'l':
                        channel.limit = 0
                        if 'L' in channel.modes:
                            channel.modes = channel.modes.replace('L', '')
                            modebuf.append('L')
                            parambuf.append(channel.redirect)
                            channel.redirect = None

                    elif m == 'k':
                        try:
                            p = recv[2:][paramcount]
                        except Exception as ex:
                            continue
                        if p != channel.key:
                            continue
                        parambuf.append(channel.key)
                        channel.key = None
                        paramcount += 1

                    elif m  == 'L':
                        channel.redirect = None

                    elif m == 'P' and len(channel.users) == 0:
                        localServer.channels.remove(channel)

                    channel.modes = channel.modes.replace(m, '')
                    modebuf.append(m)

                elif m in 'beI':
                    try:
                        # Checking both mask forms. Only for removing.
                        rawmask = recv[2:][paramcount]
                        mask = makeMask(localServer, recv[2:][paramcount])
                    except:
                        continue
                    if m == 'b':
                        data = channel.bans
                    elif m == 'e':
                        data = channel.excepts
                    elif m == 'I':
                        data = channel.invex
                    if mask in data:
                        del data[mask]
                        parambuf.append(mask)
                        modebuf.append(m)
                    elif rawmask in data:
                        del data[rawmask]
                        parambuf.append(rawmask)
                        modebuf.append(m)
                    paramcount += 1
                    continue
                elif m in chstatus:
                    timed = False
                    # -qaohv
                    try:
                        temp_user = recv[2:][paramcount]
                    except:
                        paramcount += 1
                        continue
                    try:
                        t = recv[2:][paramcount].split(':')
                        temp_user = t[0]
                        try:
                            channel.temp_status
                        except:
                            channel.temp_status = {}
                        if valid_expire(t[1]):
                            timed = valid_expire(t[1])
                    except:
                        pass
                    user = list(filter(lambda u: u.uid == temp_user or u.nickname.lower() == temp_user.lower(), channel.users))
                    if not user:
                        paramcount += 1
                        continue
                    else:
                        user = user[0]
                    if m not in channel.usermodes[user]:
                        paramcount += 1
                        continue
                    if 'S' in user.modes and not self.ocheck('o', 'override'):
                        self.sendraw(974, '{} :{} is a protected service bot'.format(m, user.nickname))
                        paramcount += 1
                        continue
                    elif 'S' in user.modes:
                        oper_override = True
                    if type(self).__name__ != 'Server':
                        if self.chlevel(channel) < modeLevel[m] and not self.ocheck('o', 'override') and user != self:
                            paramcount += 1
                            continue
                        elif self.chlevel(channel) < modeLevel[m]:
                            oper_override = True

                    channel.usermodes[user] = channel.usermodes[user].replace(m, '')
                    paramcount += 1
                    modebuf.append(m)
                    parambuf.append(user.nickname)
                    if timed:
                        channel.temp_status[user] = {}
                        channel.temp_status[user][m] = {}
                        channel.temp_status[user][m]['ctime'] = int(time.time()) + timed
                        channel.temp_status[user][m]['action'] = '+'
                    continue

        if not modebuf:
            return
        if ''.join(modebuf[-1]) in '+-':
            del modebuf[-1]

        for callable in [callable for callable in localServer.hooks if callable[0].lower() == 'pre_'+hook]:
            try:
                callable[2](self, localServer, channel, recv[1], recv[2:], modebuf, parambuf)
            except Exception as ex:
                logging.exception(ex)

        if channel.name[0] == '&':
            sync = False
        modes = ''.join(modebuf)
        total_modes, total_params = [], []
        if len(modebuf) > 1:
            mode_limit = modes.replace('+', '').replace('-', '')
            total_modes, total_params = [], []
            paramcount = 0
            action = ''
            for m in modes:
                if m in '+-':
                    action = m
                    total_modes.append(m)
                    continue
                if action == '+':
                    thook = 'modechar_add'
                elif action == '-':
                    thook = 'modechar_del'
                for callable in [callable for callable in localServer.hooks if callable[0].lower() == thook]:
                    try:
                        callable[2](channel, m)
                    except Exception as ex:
                        logging.exception(ex)
                for callable in [callable for callable in localServer.hooks if callable[0].lower() == hook]:
                    try:
                        callable[2](self, localServer, channel, modes, parambuf)
                    except Exception as ex:
                        logging.exception(ex)
                if m in localServer.parammodes:
                    total_params.append(parambuf[paramcount])
                    paramcount += 1
                total_modes.append(m)
                totalLength = len(''.join(total_modes)+' '+' '.join(total_params))
                mode_amount = len(re.sub('[+-]', '', ''.join(total_modes)))
                if mode_amount >= maxmodes or totalLength >= 400:
                    all_modes = ''.join(total_modes)+' '+' '.join(total_params)
                    if oper_override and type(self).__name__ != 'Server':
                        sourceServer.snotice('s', '*** OperOverride by {} ({}@{}) with MODE {} {}'.format(sourceUser.nickname, sourceUser.ident, sourceUser.hostname, channel.name, all_modes))
                    if sync:
                        localServer.new_sync(localServer, sourceServer, ':{} MODE {} :{}'.format(displaySource, channel.name, all_modes if type(self).__name__ == 'User' else rawModes))
                    sourceUser.broadcast(channel.users, 'MODE {} {}'.format(channel.name, all_modes), source=sourceUser)
                    total_modes, total_params = [action], []
                    continue
            if len(total_modes) > 1:
                all_modes = ''.join(total_modes)+' '+' '.join(total_params)
                if oper_override and type(self).__name__ != 'Server':
                    sourceServer.snotice('s', '*** OperOverride by {} ({}@{}) with MODE {} {}'.format(sourceUser.nickname, sourceUser.ident, sourceUser.hostname, channel.name, all_modes))
                if sync:
                    localServer.new_sync(localServer, sourceServer, ':{} MODE {} :{}'.format(displaySource, channel.name, all_modes if type(self).__name__ == 'User' else rawModes))
                sourceUser.broadcast(channel.users, 'MODE {} {}'.format(channel.name, all_modes), source=sourceUser)

            for cmd, data in commandQueue:
                localServer.handle(cmd, data)

    except Exception as ex:
        logging.exception(ex)

@ircd.Modules.params(1)
@ircd.Modules.support(('CHANMODES=', True)) ### (support string, boolean if support must be sent to other servers)
@ircd.Modules.support('MAXLIST=')
@ircd.Modules.support('PREFIX=')
@ircd.Modules.support('MODES='+str(maxmodes))
@ircd.Modules.commands('mode')
def mode(self, localServer, recv, override=False, handleParams=None):
    global oper_override
    oper_override = False
    try:
        if type(self).__name__ == 'Server':
            sourceServer = self
            S = recv[0][1:]
            sourceUser = [s for s in localServer.servers+[localServer] if s.sid == S or s.hostname == S]+[u for u in localServer.users if u.uid == S or u.nickname == S]
            if sourceUser:
                sourceUser = sourceUser[0]
            else:
                sourceUser = self
            target = recv[2]
            if target[0] in localServer.chantypes:
                channel = list(filter(lambda c: c.name.lower() == recv[2].lower(), localServer.channels))
                if not channel:
                    return
                processModes(self, localServer, channel[0], recv[2:], sourceServer=sourceServer, sourceUser=sourceUser)
                return
            recv = recv[1:]
        else:
            sourceServer = self.server
            sourceUser = self
        #recv = ' '.join(recv).split() # Why?

        chstatus = localServer.chstatus
        if len(recv) == 2 and recv[1][:1] in localServer.chantypes:
            if recv[1][0] == '+':
                return
            channel = list(filter(lambda c: c.name.lower() == recv[1].lower(), localServer.channels))
            if not channel:
                return self.sendraw(401, '{} :No such channel'.format(recv[1]))
            channel = channel[0]
            if 's' in channel.modes and self not in channel.users and not self.ocheck('o', 'override'):
                return
            params = []
            for m in channel.modes:
                if m == 'l':
                    params.append(str(channel.limit))
                elif m == 'L':
                    params.append(str(channel.redirect))
                elif m == 'f':
                    error = False
                    fparams = '['
                    if len(channel.chmodef) == 0:
                        error = True
                    for t in channel.chmodef:
                        fstring = '{}:{}:{}'.format(channel.chmodef[t]['amount'], t, channel.chmodef[t]['time'])
                        #print('fstring set: {}'.format(fstring))
                        if channel.chmodef[t]['action']:
                            try:
                                fstring += ':{}:{}'.format(channel.chmodef[t]['action'], channel.chmodef[t]['duration'])
                            except KeyError:
                                ### Entry has no 'duration'.
                                fparams += fstring+','
                                continue
                            except Exception as ex:
                                error = True
                                #print('t: {} -- {}'.format(t, ex))
                        fparams += fstring+','
                    if not error:
                        fparams = fparams[:-1]
                        fparams += ']'
                        params.append(fparams)
                elif m == 'k':
                    params.append(channel.key)
            self.sendraw(324, '{} +{} {}'.format(channel.name, channel.modes,' '.join(params) if len(params) > 0 and (self in channel.users or 'o' in self.modes) else ''))
            self.sendraw(329, '{} {}'.format(channel.name, channel.creation))
            return

        elif recv[1][0] not in localServer.chantypes:
            user = list(filter(lambda u: u.nickname.lower() == recv[1].lower() or u.uid == recv[1], localServer.users))
            if not user:
                return

            if user[0] != self and sourceServer == localServer and not localServer.ocheck('o', 'remotemode') and type(self).__name__ != 'Server':
                return
            chgumode(self, localServer, recv, override, sourceServer=sourceServer, sourceUser=sourceUser)
            for callable in [callable for callable in localServer.events if callable[0].lower() == recv[0].lower()]:
                try:
                    callable[1](self, localServer, recv)
                except Exception as ex:
                    logging.exception(ex)
            return

        ######################
        ### CHANNEL MODES ####
        ######################
        channel = list(filter(lambda c: c.name.lower() == recv[1].lower(), localServer.channels))
        if not channel:
            return self.sendraw(401, '{} :No such channel'.format(recv[1]))

        channel = channel[0]
        if type(self).__name__ == 'Server' and not self.eos and self != localServer:
            return

        if type(self).__name__ != 'Server':
            if self not in channel.users and not self.ocheck('o', 'override'):
                return self.sendraw(401, '{} :No such channel'.format(recv[1]))

        if len(recv) == 3:
            if recv[2] == '+b' or recv[2] == 'b':
                for entry in channel.bans:
                    self.sendraw(367, '{} {} {} {}'.format(channel.name, entry, channel.bans[entry]['setter'], channel.bans[entry]['ctime']))
                return self.sendraw(368, '{} :End of Channel Ban List'.format(channel.name))
            elif recv[2] == '+e' or recv[2] == 'e':
                if self.chlevel(channel) < 3 and not self.ocheck('o', 'override'):
                    return self.sendraw(482, '{} :You are not allowed to view the excepts list'.format(channel.name))
                for entry in channel.excepts:
                    self.sendraw(348, '{} {} {} {}'.format(channel.name, entry, channel.excepts[entry]['setter'], channel.excepts[entry]['ctime']))
                return self.sendraw(349, '{} :End of Channel Exceptions List'.format(channel.name))
            elif recv[2] == '+I' or recv[2] == 'I':
                if self.chlevel(channel) < 3 and not self.ocheck('o', 'override'):
                    return self.sendraw(482, '{} :You are not allowed to view the invex list'.format(channel.name))
                for entry in channel.invex:
                    self.sendraw(346, '{} {} {} {}'.format(channel.name, entry, channel.invex[entry]['setter'], channel.invex[entry]['ctime']))
                return self.sendraw(347, '{} :End of Channel Invite List'.format(channel.name))

        if type(self).__name__ != 'Server':
            if self.chlevel(channel) < 2 and not self.ocheck('o', 'override'):
                   return self.sendraw(482, '{} :You\'re not a channel operator'.format(channel.name))
            elif self.chlevel(channel) < 2:
                oper_override = True
        processModes(self, localServer, channel, recv[1:], sourceServer=sourceServer, sourceUser=sourceUser)

    except Exception as ex:
        logging.exception(ex)

def chgumode(self, localServer, recv, override, sourceServer=None, sourceUser=None):
    try:
        modes = []
        action = ''
        target = list(filter(lambda u: u.nickname.lower() == recv[1].lower(), localServer.users))
        if not target:
            return

        target = target[0]

        if type(self).__name__ == 'Server':
            override = True
            displaySource = self.hostname
            if self != localServer:
                displaySource = sourceUser.nickname
        else:
            if self.server != localServer:
                override = True
            displaySource = self.nickname
        self = sourceUser
        warn = []
        unknown = []
        showsno = False
        for m in str(recv[2]):
            if 'modelock' in localServer.conf['settings'] and m in localServer.conf['settings']['modelock'] and not self.ocheck('o', 'override') and not override:
                if 'lock' not in warn:
                    warn.append('lock')
                    localServer.broadcast([self], 'NOTICE {} :The following modes cannot be changed: \'{}\''.format(self.nickname, localServer.conf['settings']['modelock']))
                    warn = []
                continue

            if m == 'r' and type(self).__name__ != 'Server':
                if self.server.hostname not in localServer.conf['settings']['ulines']:
                    continue
            if m in '+-' and action != m:
                action = m
                try:
                    if modes[-1] in '+-':
                        del modes[-1]
                except:
                    pass
                modes.append(action)
            else:
                if m not in '+-' and m not in localServer.user_modes and type(self).__name__ != 'Server':
                    if m not in unknown and not override:
                        unknown.append(m)
                    continue
                if m in 'z' and not override:
                    if m not in warn:
                        self.sendraw(501, 'Mode +{} may only be set by servers'.format(m))
                        warn.append(m)
                    continue
                    warn = []
                if m in 'ohsqHW' and (not self.operaccount or m not in localServer.conf['opers'][self.operaccount]['modes']) and not override:
                    continue
                if action == '+':
                    if m == 'x':
                        cloaked = cloak(localServer, self.hostname)
                        self.setinfo(cloaked, t='host', source=sourceServer)
                        self.cloakhost = cloaked
                    elif m == 'S' and self.server.hostname not in localServer.conf['settings']['ulines']:
                        self.sendraw(501, 'Mode +{} may only be set by servers'.format(m))
                        continue
                    elif m == 's':
                        if len(recv) > 3:
                            for s in recv[3]:
                                if s in '+-':
                                    saction = s
                                    continue
                                if saction == '-' and s in target.snomasks:
                                    showsno = True
                                    target.snomasks = target.snomasks.replace(s, '')
                                    continue
                                if saction == '+' and s in localServer.snomasks and (self.operaccount and s in localServer.conf['opers'][self.operaccount]['snomasks']) and s not in target.snomasks:
                                    showsno = True
                                    target.snomasks += s
                                    continue

                    if m not in target.modes:
                        if m in 'sqHSW' and (not hasattr(target, 'opermodes') or m not in target.opermodes):
                            if not hasattr(target, 'opermodes'):
                                target.opermodes = ''
                            target.opermodes += m
                        target.modes += m
                        modes.append(m)

                if action == '-' and m in target.modes:
                    if m == 'x':
                        self.setinfo(self.hostname, t='host', source=sourceServer)
                    elif m == 'S' and self.server.hostname not in localServer.conf['settings']['ulines']:
                        self.sendraw(501, 'Mode +{} may only be set by servers'.format(m))
                        continue
                    elif m == 'r':
                        target.svid = '*'
                    elif m == 's':
                        target.snomasks = ''
                    elif m == 'o':
                        target.operflags = []
                        ### Assign a class.
                        for cls in localServer.conf['allow']:
                            clientmaskhost = '{}@{}'.format(target.ident, target.ip)
                            if 'ip' in localServer.conf['allow'][cls]:
                                clientmask = '{}@{}'.format(target.ident, target.ip)
                                isMatch = match(localServer.conf['allow'][cls]['ip'], clientmask)
                            if 'hostname' in localServer.conf['allow'][cls]:
                                clientmask = '{}@{}'.format(target.ident, target.hostname)
                                isMatch = match(localServer.conf['allow'][cls]['hostname'], clientmask)
                            if isMatch:
                                if 'options' in localServer.conf['allow'][cls]:
                                    if 'ssl' in localServer.conf['allow'][cls]['options'] and not target.ssl:
                                        continue
                                target.cls = cls

                        if hasattr(target, 'opermodes'):
                            for mode in [m for m in target.opermodes if m in target.modes]:
                                modes.append(mode)
                                if mode == 's':
                                    target.snomasks = ''
                        if target.swhois:
                            operSwhois = ''
                            if 'swhois' in localServer.conf['opers'][target.operaccount]:
                                operSwhois = localServer.conf['opers'][target.operaccount]['swhois']
                            if operSwhois in target.swhois:
                                target.swhois.remove(operSwhois)
                            if target.operswhois in target.swhois:
                                target.swhois.remove(target.operswhois)
                            data = ':{} SWHOIS {} :'.format(localServer.sid, target.uid)
                            localServer.new_sync(localServer, sourceServer, data)
                            for line in target.swhois:
                                data = ':{} SWHOIS {} :{}'.format(localServer.sid, target.uid, line)
                                localServer.new_sync(localServer, sourceServer, data)

                        target.opermodes = ''
                        self.operaccount = None

                    if m not in modes:
                        modes.append(m)
                    # Removing modes from user class.
                    for mode in modes:
                        target.modes = target.modes.replace(mode, '')
        if 'o' in target.modes:
            target.modes = 'o'+target.modes.replace('o', '')
        if ' '.join(modes)[-1] in '+-':
            del modes[-1]
        modes = ''.join(modes)
        if len(modes) > 1:
            target._send(':{} MODE {} :{}'.format(displaySource, target.nickname, modes))
            if self != target:
                self.sendraw(501, 'UMODE {} :{}'.format(target.nickname, modes))

            if target.server != localServer:
                localServer.new_sync(localServer, sourceServer, ':{} MODE {} {}'.format(displaySource, target.nickname, modes))
            else:
                localServer.new_sync(localServer, sourceServer, ':{} UMODE2 {}'.format(target.uid, modes))

            for callable in [callable for callable in localServer.events if callable[0].lower() == 'umode']:
                try:
                    callable[1](target, localServer, modes)
                except Exception as ex:
                    logging.exception(ex)

        if 's' in modes or showsno:
            localServer.new_sync(localServer, sourceServer, ':{} BV +{}'.format(target.uid, target.snomasks))
            target.sendraw(8, 'Server notice mask (+{})'.format(target.snomasks))

        if unknown:
            self.sendraw(501, 'Mode{} \'{}\' not found'.format('s' if len(unknown) > 1 else '', ''.join(unknown)))

    except Exception as ex:
        logging.exception(ex)
