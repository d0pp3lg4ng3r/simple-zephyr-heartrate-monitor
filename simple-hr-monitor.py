# So, whoever wrote the zephyr python library didn't do a lot of commenting in
#   their files to document how to use the library.  I'm extremely grateful to
#   jpaalasm for writing the library (I couldn't have done better in the time I
#   have), but I will try to comment my exploration so that anyone who reads my
#   source code can have a head-start in making heads and tails of it.
#       - Ryan Fredette (d0pp3lg4ng3r)

import zephyr
from zephyr.collector import MeasurementCollector
from zephyr.bioharness import (
        BioHarnessSignalAnalysis,
        BioHarnessPacketHandler
    )
from zephyr.delayed_stream import DelayedRealTimeStream
from zephyr.message import MessagePayloadParser
from zephyr.protocol import (
        BioHarnessProtocol,
        MessageFrameParser
    )
from zephyr.hxm import HxMPacketAnalysis

from serial import Serial
from serial.serialutil import SerialException

from sys import argv, stdout, stderr

import os

class Callback(object):
    def __init__(self, filename):
        # open file
        self.outfile = open(filename, 'a')
        #self.outfile = stdout

    def callback(self, value_name, value):
        if value_name == "heart_rate":
            self.outfile.write("%s\n" % value)
            self.outfile.flush()
            os.fsync(self.outfile)
        else:
            stderr.write("%s: %s\n" % (value_name, value))


def main():
    # This big try: ... finally: ... block is to guarantee that we properly
    #   close all our connections (open files, HxM BT)
    try:
        # Parse args. Expects args as:
        #       $ pyzephyr_test.py <serial-port-number> <output-file>
        #   <serial-port-number> is the X in COM<X> (COM1 = 1, COM2 = 2, etc.)
        #   <output-file is the file to append the output to.  This arg is
        #       currently ignored.
        com_number = 0
        try:
            com_number = int(argv[1])
        except ValueError:
            print("'%s' is not a valid number.  Please only input the number of the serial port."
                    % argv[1])
            return 1
        output_file = argv[2]
        # Open the serial connection.
        serial_conn = None
        try:
            serial_conn = Serial(com_number - 1, timeout=30)
        except SerialException, e:
            print("Could not open COM%d.  Are you sure it is the fitness monitor?"
                    % com_number)
            print("Error: %s" % str(e))
            return 1
        # Create a callback object.  We need it to store state (the file it
        #   writes to), so it needs to be an object.
        mycallback = Callback(output_file)
        # Collects measurements (what does this entail?)
        collector = MeasurementCollector()
        # Analyzes R-R intervals (time for 1 heartbeat)
        rr_signal_analysis = BioHarnessSignalAnalysis([], [collector.handle_event])
        # Handles incoming BioHarness payloads.  I guess it will parse them
        #   into a common format, then send them to the collector and
        #   rr_signal_analysis signal handlers.
        signal_packet_handler_bh = BioHarnessPacketHandler([collector.handle_signal,
                rr_signal_analysis.handle_signal], [collector.handle_event])
        # Handles incoming HxM payloads.  I guess it will also parse these
        #   packets into a common format, then send them to the collector event
        #   handler.
        signal_packet_handler_hxm = HxMPacketAnalysis([collector.handle_event])
        # Seems to be the actual parsing step.  It will extract the 'payload'
        #   from the serial messages, then send them to each packet handler.  I
        #   assume each packet handler will only take one type of packet that
        #   the device sends, but it seems to send multiple types of packets.
        payload_parser = MessagePayloadParser([
                signal_packet_handler_bh.handle_packet,
                signal_packet_handler_hxm.handle_packet])
        message_parser = MessageFrameParser(payload_parser.handle_message)
        # Some method of getting the real time data from the serial stream, and
        #   doing... something with it.  It seems to be the incoming data from
        #   the device.
        delayed_stream_thread = DelayedRealTimeStream(collector,
                [mycallback.callback], 1.2)
        # This seems to be the outgoing data (to the device).  We need to
        #   initialize it in order for it to start sending packets.
        protocol = BioHarnessProtocol(serial_conn, [message_parser.parse_data])
        # The meat of the operation.  Here we tell the biometric monitor (HxM)
        #   to start sending us data.
        protocol.enable_periodic_packets()
        # Here we start running the other thread, where we receive the raw
        #   input, and set it to a known interval (I'm not sure why this is
        #   important)
        delayed_stream_thread.start()
        # This try: ... except: ... block is responsible for the parsing of
        #   data from the biometric monitor.  It will read data until an EOF
        #   (End of File) is reached, which I guess means that the device has
        #   stopped sending data altogether.
        try:
            protocol.run()
        except EOFError:
            pass
    finally:
        # Once the device has stopped sending data, we close our serial
        #   connection, and stop the other thread
        serial_conn.close()
        delayed_stream_thread.terminate()
        # Then wait for it to finish.
        delayed_stream_thread.join()
    return 0

if __name__ == '__main__':
    main()
