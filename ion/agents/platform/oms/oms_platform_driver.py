#!/usr/bin/env python

"""
@package ion.agents.platform.oms.oms_platform_driver
@file    ion/agents/platform/oms/oms_platform_driver.py
@author  Carlos Rueda
@brief   Base class for OMS platform drivers.
"""

__author__ = 'Carlos Rueda'
__license__ = 'Apache 2.0'


from pyon.public import log

from ion.agents.platform.platform_driver import PlatformDriver
from ion.agents.platform.exceptions import PlatformException
from ion.agents.platform.exceptions import PlatformDriverException
from ion.agents.platform.exceptions import PlatformConnectionException
from ion.agents.platform.oms.oms_resource_monitor import OmsResourceMonitor
from ion.agents.platform.oms.oms_client_factory import OmsClientFactory
from ion.agents.platform.util.network import NNode


class OmsPlatformDriver(PlatformDriver):
    """
    Base class for OMS platform drivers.
    """

    def __init__(self, platform_id, driver_config):
        """
        Creates an OmsPlatformDriver instance.

        @param platform_id Corresponding platform ID
        @param driver_config with required 'oms_uri' entry.
        """
        PlatformDriver.__init__(self, platform_id)

        if not 'oms_uri' in driver_config:
            raise PlatformDriverException(msg="driver_config does not indicate 'oms_uri'")

        oms_uri = driver_config['oms_uri']
        log.info("%r: creating OmsClient instance with oms_uri=%r" % (
            self._platform_id, oms_uri))
        self._oms = OmsClientFactory.create_instance(oms_uri)
        log.info("%r: OmsClient instance created: %s" % (
            self._platform_id, self._oms))

        # TODO set-up configuration for notification of events associated
        # with values retrieved during platform resource monitoring

        # _monitors: dict { attr_id: OmsResourceMonitor }
        self._monitors = {}

    def go_active(self):

        log.info("%r: go_active: pinging..." % self._platform_id)
        try:
            retval = self._oms.hello.ping()
        except Exception, e:
            raise PlatformConnectionException("Cannot ping %s" % str(e))

        if retval is None or retval.lower() != "pong":
            raise PlatformConnectionException(
                "Unexpected ping response: %r" % retval)

        log.info("%r: getting platform map..." % self._platform_id)
        try:
            map = self._oms.config.getPlatformMap()
        except Exception, e:
            raise PlatformConnectionException("error getting platform map %s" % str(e))

        self._build_network_definition(map)

        log.info("%r: go_active completed ok." % self._platform_id)

    def _build_network_definition(self, map):
        """
        Assigns self._nnode according to self._platform_id and the OMS'
        getPlatformMap response.
        """
        nodes = NNode.create_network(map)
        if not self._platform_id in nodes:
            raise PlatformException(
                "platform map does not contain entry for %r" % self._platform_id)

        self._nnode = nodes[self._platform_id]
        log.info("%r: _nnode:\n %s" % (self._platform_id, self._nnode.dump()))

    def start_resource_monitoring(self):
        """
        Starts greenlets to periodically retrieve values of the attributes
        associated with my platform, and do corresponding event notifications.
        """
        # TODO preliminary implementation. General idea:
        # - get attributes for the platform
        # - aggregate groups of attributes according to rate of monitoring
        # - start a greenlet for each attr grouping

        log.info("%r: starting resource monitoring" % self._platform_id)

        # get names of attributes associated with my platform
        attr_names = self._oms.getPlatformAttributeNames(self._platform_id)

        # get info associated with these attributes
        platAttrMap = {self._platform_id: attr_names}
        retval = self._oms.getPlatformAttributeInfo(platAttrMap)

        log.info("%r: getPlatformAttributeInfo= %s" % (
            self._platform_id, retval))

        if not self._platform_id in retval:
            raise PlatformException("Unexpected: response does not include "
                                    "requested platform '%s'" % self._platform_id)

        #
        # TODO attribute grouping so one single greenlet is launched for a
        # group of attributes having same or similar monitoring rate. For
        # simplicity at the moment, start a greenlet per attribute.
        #

        attr_info = retval[self._platform_id]
        for attr_name, attr_defn in attr_info.iteritems():
            if 'monitorCycleSeconds' in attr_defn:
                self._start_monitor_greenlet(attr_defn)
            else:
                log.warn(
                    "%r: unexpected: attribute info does not contain %r "
                    "for attribute %r. attr_defn = %s" % (
                        self._platform_id,
                        'monitorCycleSeconds', attr_name, str(attr_defn)))

    def _start_monitor_greenlet(self, attr_defn):
        assert 'attr_id' in attr_defn
        assert 'monitorCycleSeconds' in attr_defn
        resmon = OmsResourceMonitor(self._oms, self._platform_id, attr_defn,
                                    self._notify_driver_event)
        self._monitors[attr_defn['attr_id']] = resmon
        resmon.start()

    def stop_resource_monitoring(self):
        """
        Stops all the monitoring greenlets.
        """
#        assert self._oms is not None, "set_oms_client must have been called"

        log.info("%r: stopping resource monitoring" % self._platform_id)
        for resmon in self._monitors.itervalues():
            resmon.stop()
        self._monitors.clear()