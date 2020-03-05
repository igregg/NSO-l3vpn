# -*- mode: python; python-indent: 4 -*-
import ncs
from ncs.application import Service


# ------------------------
# SERVICE CALLBACK EXAMPLE
# ------------------------
class ServiceCallbacks(Service):

    # The create() callback is invoked inside NCS FASTMAP and
    # must always exist.
    @Service.create
    def cb_create(self, tctx, root, service, proplist):
        # import pydevd_pycharm
        # pydevd_pycharm.settrace('localhost', port=30000, stdoutToServer=True, stderrToServer=True)
        self.log.info('Service create(service=', service._path, ')')

        service_name = service.name
        self.log.info('Provisioning L3VPN-PWHE Service custommer ID:', service_name)

        ### PE Global ###
        pe = service.pe
        pe_name = pe.name
        vrf = pe.vrf
        rd = pe.rd
        max_prefix = pe.max_prefix
        pe_loopback = self.get_ip_loopback(root, service, pe_name, 'cisco-iosxr')

        ### PE BVI Intf ###
        interface = pe.interface
        bvi_num = interface.bvi
        bvi_bw = interface.bandwidth
        bvi_ip = interface.ip_address
        bvi_netmask = interface.netmask
        bvi_desc = interface.description if interface.description is not None else 'Configure from NSO'
        bvi_policy_in = interface.policy_in
        bvi_policy_out = interface.policy_out

        ### PE Routing ###
        routing = pe.routing_protocol
        prefix_list = list()

        if routing == 'static':
            static = pe.static
            for prefix in static.statics:
                prefix_list.append({'prefix': prefix.prefix, 'next_hop': prefix.next_hop})
                # prefix_list['prefix'] = prefix.prefix
                # prefix_list['next_hop'] = prefix.next_hop
        elif routing == 'bgp':
            bgp = pe.bgp
            customer_as = bgp.customer_as

        ### L2VPN ###
        l2vpn = service.l2vpn
        vcid = l2vpn.vcid
        endpoint = l2vpn.endpoint
        for device in endpoint:
            lpe_name = device.name
            description = device.description if device.description is not None else 'Configure from NSO'
            instance_id = device.instance_id
            platform = self.get_device_platform(root, service, lpe_name)
            local_ip_loopback = self.get_ip_loopback(root, service, lpe_name, platform)
            interface_type, interface_num = self.get_interface(root, service, device, platform)
            encapsulation = device.encapsulation
            vlan = device.vlan_id
            mtu = device.mtu
            l2_policy_in = device.policy_in
            l2_policy_out = device.policy_out

            l2vpn_vars = ncs.template.Variables()
            l2vpn_vars.add('PE', pe_name)
            l2vpn_vars.add('LPE', lpe_name)
            l2vpn_vars.add('VRF', vrf)
            l2vpn_vars.add('BVI_NUM', bvi_num)
            l2vpn_vars.add('REMOTE_LB', local_ip_loopback)
            l2vpn_vars.add('DESCRIPTION', description)
            l2vpn_vars.add('INST_ID', instance_id)
            l2vpn_vars.add('VC_ID', vcid)
            l2vpn_vars.add('INTERFACE_TYPE', interface_type)
            l2vpn_vars.add('INTERFACE_NUM', interface_num)
            l2vpn_vars.add('ENCAPSULATION', encapsulation)
            l2vpn_vars.add('VLAN', vlan)
            l2vpn_vars.add('MTU', mtu)
            l2vpn_vars.add('POLICY_IN', l2_policy_in)
            l2vpn_vars.add('POLICY_OUT', l2_policy_out)
            l2vpn_vars.add('PE_LB', pe_loopback)

            template = ncs.template.Template(service)
            template.apply('l3vpn-pwhe-l2vpn', l2vpn_vars)

        l3vpn_vars = ncs.template.Variables()
        l3vpn_vars.add('PE', pe_name)
        l3vpn_vars.add('VRF', vrf)
        l3vpn_vars.add('MAX_PREFIX', max_prefix)
        l3vpn_vars.add('BVI_NUM', bvi_num)
        l3vpn_vars.add('BW', bvi_bw)
        l3vpn_vars.add('DESCRIPTION', bvi_desc)
        l3vpn_vars.add('IP', bvi_ip)
        l3vpn_vars.add('NETMASK', bvi_netmask)
        l3vpn_vars.add('BVI_POLICY_IN', bvi_policy_in)
        l3vpn_vars.add('BVI_POLICY_OUT', bvi_policy_out)
        l3vpn_vars.add('ROUTING', routing)
        l3vpn_vars.add('RD', rd)
         
        if routing == 'static':
            for prefix in prefix_list:
                l3vpn_vars.add('PREFIX', prefix['prefix'])
                l3vpn_vars.add('NEXTHOP', prefix['next_hop'])
                template = ncs.template.Template(service)
                template.apply('l3vpn-pwhe-pe', l3vpn_vars)
        elif routing == 'bgp':
            template.apply('l3vpn-pwhe-pe', l3vpn_vars)
        else:
            template.apply('l3vpn-pwhe-pe', l3vpn_vars)

    def get_interface(self, root, service, device, platform):
        """
        Get interface type and interface number
        :param root:
        :param service:
        :param device:
        :param platform:
        :return:
        """
        interface_type = ''
        interface_num = ''

        if platform == 'cisco-ios':
            interface = device.interface_ios
        elif platform == 'cisco-iosxr':
            interface = device.interface_ios_xr
        else:
            return None, None

        for int_type in interface:
            if int_type.endswith('Ethernet'):
                int_type = int_type.split(':')[-1]
                if interface[int_type] is not None:
                    interface_type = int_type
                    interface_num = interface[int_type]

        return interface_type, interface_num
    
    def get_device_platform(self, root, service, device_name):
        """
        Get device platform by looking in capability. eg: urn:ios, http://tail-f.com/ned/cisco-ios-xr.
        :param root:
        :param service:
        :return: dict of { device_name: str:platform, ... }
        """
        self.log.debug(" Executing in Module: get_device_platform ")

        device_platform = ''
        device_capability = root.devices.device[device_name].capability
        if 'urn:ios' in device_capability:
            device_platform = 'cisco-ios'
        elif 'http://tail-f.com/ned/cisco-ios-xr' in device_capability:
            device_platform = 'cisco-iosxr'
        else:
            self.log.debug("No device platform was found.")

        return device_platform

    def get_ip_loopback(self, root, service, device_name, platform, loopback_id=0):
        """
        Get IPv4 from interface loopback (default=0)
        :param root:
        :param service:
        :return:
        """
        self.log.debug(" Executing in Module: get_ip_loopback ")

        ip_loopback = ''
        device_loopback_config = root.devices.device[device_name].config.interface.Loopback[str(loopback_id)]
        if platform == 'cisco-ios':
            ip_loopback = device_loopback_config.ip.address.primary.address
        if platform == 'cisco-iosxr':
            ip_loopback = device_loopback_config.ipv4.address.ip

        return ip_loopback

    def get_remote_ip_loopback(self, root, service, local_device, endpoint, loopback_id=0):
        """
        :param root:
        :param service:
        :param local: Device name
        :param endpoint: list of Devices
        :param loopback_id: default=0
        :return:
        """
        endpoints = endpoint
        remote_ip_loopback = dict()

        for endpoint in endpoints:
            device_name = endpoint.device
            if device_name != local_device:
                platform = self.get_device_platform(root, service, device_name)
                remote_ip_loopback[device_name] = self.get_ip_loopback(root, service, device_name, platform)

        return remote_ip_loopback

    # The pre_modification() and post_modification() callbacks are optional,
    # and are invoked outside FASTMAP. pre_modification() is invoked before
    # create, update, or delete of the service, as indicated by the enum
    # ncs_service_operation op parameter. Conversely
    # post_modification() is invoked after create, update, or delete
    # of the service. These functions can be useful e.g. for
    # allocations that should be stored and existing also when the
    # service instance is removed.

    # @Service.pre_lock_create
    # def cb_pre_lock_create(self, tctx, root, service, proplist):
    #     self.log.info('Service plcreate(service=', service._path, ')')

    # @Service.pre_modification
    # def cb_pre_modification(self, tctx, op, kp, root, proplist):
    #     self.log.info('Service premod(service=', kp, ')')

    # @Service.post_modification
    # def cb_post_modification(self, tctx, op, kp, root, proplist):
    #     self.log.info('Service premod(service=', kp, ')')


# ---------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS.
# ---------------------------------------------
class Main(ncs.application.Application):
    def setup(self):
        # The application class sets up logging for us. It is accessible
        # through 'self.log' and is a ncs.log.Log instance.
        self.log.info('Main RUNNING')

        # Service callbacks require a registration for a 'service point',
        # as specified in the corresponding data model.
        #
        self.register_service('l3vpn-servicepoint', ServiceCallbacks)

        # If we registered any callback(s) above, the Application class
        # took care of creating a daemon (related to the service/action point).

        # When this setup method is finished, all registrations are
        # considered done and the application is 'started'.

    def teardown(self):
        # When the application is finished (which would happen if NCS went
        # down, packages were reloaded or some error occurred) this teardown
        # method will be called.

        self.log.info('Main FINISHED')
