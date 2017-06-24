#!/usr/bin/env python

'''
a module for reliable block data sending over UDP

NOTE: This module should only be used on private networks - it takes
no account of network congestion.

The protocol is designed to work well with large amounts of packet loss, while
using a fixed maximum bandwidth. The actual send bandwidth scales closely
as the target bandwidth times the packet loss.

The protocol sends arbitrary "blocks" of data. It was designed for
sending images and telemetry data efficiently over a lossy wireless
link. The default transport is UDP, but the user can specify their own
message oriented transport if needed. 

Andrew Tridgell
May 2012
released under the GNU GPL v3 or later
'''

import socket, select, os, random, time, random, struct, binascii

# packet types - first byte of a packet
PKT_ACK = 0
PKT_COMPLETE = 1
PKT_CHUNK = 2

# size of packet type plus crc32
PACKET_HEADER_SIZE = 5

class BlockSenderException(Exception):
    '''block sender error class'''
    def __init__(self, msg):
        Exception.__init__(self, msg)


class BlockSenderSet:
    '''hold a set of chunk IDs for an identifier.
    This object is sent as a PKT_ACK to
    acknowledge receipt of data'''
    def __init__(self, id, num_chunks, mss):
        self.id = id
        self.num_chunks = num_chunks
        self.chunks = set()
        self.timestamp = 0
        self.format = '<QHd'
        self.header_size = struct.calcsize(self.format)
        self.first_missing = 0
        self.mss = mss
        self.last_sent = 0
                #print("Created %s" % str(self))

    def __str__(self):
        return 'BlockSenderSet<%u/%u>' % (len(self.chunks), self.num_chunks)

    def update_first_missing(self):
        '''update the first_missing field'''
        while self.first_missing < self.num_chunks:
            if not self.first_missing in self.chunks:
                break
            self.first_missing += 1

    def add(self, chunk_id, ack_to):
        '''add an extent to the list. This is called when we receive a chunk of data'''
        self.chunks.add(chunk_id)
        self.first_missing = ack_to

    def update(self, new):
        '''add in new chunks. This is called when we receive an ack packet'''
        self.chunks.update(new.chunks)
        self.update_first_missing()

    def present(self, chunk_id):
        '''see if a chunk_id is present in the chunks'''
        return chunk_id in self.chunks

    def complete(self):
        '''return True if the chunks cover the whole set of data'''
        return len(self.chunks) == self.num_chunks

    def started(self):
        '''return True if we have at least one chunk'''
        return len(self.chunks) > 0

    def pack(self):
        '''return a linearized representation'''
        chunks = list(self.chunks)
        chunks.sort()
        extents = []
        for i in range(len(chunks)):
            if chunks[i] < self.first_missing:
                continue
            if len(extents) == 0:
                extents.append((chunks[i], 1))
                continue
            (first,count) = extents[-1]
            if chunks[i] == first+count:
                extents[-1] = (first, count+1)
            else:
                extents.append((chunks[i], 1))
        buf = bytes(struct.pack(self.format, self.id, self.num_chunks, self.timestamp))
        if self.mss:
            max_extents = (self.mss - (len(buf) + PACKET_HEADER_SIZE)) / 2
            if max_extents > len(extents):
                # not all of the extents will fit. Use last_sent to choose which ones
                # to send
                while len(extents) > max_extents:
                    (first,count) = extents[0]
                    if first > self.last_sent:
                        break
                    extents.pop(0)
        sent_all = True
        for (first,count) in extents:
            buf += bytes(struct.pack('<HH', first, count))
            self.last_sent = first
            if self.mss and (len(buf)+PACKET_HEADER_SIZE) + 4 > self.mss:
                sent_all = False
                break
        if sent_all:
            self.last_sent = 0
        return buf

    def unpack(self, buf):
        '''unpack a linearized representation into the object'''
        if len(buf) < self.header_size:
            raise BlockSenderException('buffer too short')
        (self.id, self.num_chunks, self.timestamp) = struct.unpack_from(self.format, buf)
        ofs = self.header_size
        if (len(buf) - ofs) % 4 != 0:
            raise BlockSenderException('invalid extents length')
        n = (len(buf) - ofs) // 4
        for i in range(n):
            (first, count) = struct.unpack_from('<HH', buf, ofs)
            ofs += 4
            for j in range(first, first+count):
                self.chunks.add(j)


class BlockSenderComplete:
    '''a packet to say that a block is complete.
    This is a bit more efficient than sending a complete extents list'''
    def __init__(self, block_id, timestamp, dest):
        self.block_id = block_id
        self.timestamp = timestamp
        self.dest = dest
                #print("Created %s" % str(self))

    def __str__(self):
        return 'BlockSenderComplete<%u>' % self.block_id

    def pack(self):
        '''return a linearized representation'''        
        return bytes(struct.pack('<Qd', self.block_id, self.timestamp))

    def unpack(self, buf):
        '''unpack a linearized representation into the object'''
        (self.block_id, self.timestamp) = struct.unpack('<Qd', buf)


class BlockSenderChunk:
    '''an incoming chunk packet. This is the main data format'''
    def __init__(self, block_id, size, chunk_id, data, chunk_size, ack_to, timestamp):
        self.block_id = block_id
        self.size = size
        self.chunk_id = chunk_id
        self.chunk_size = chunk_size
        self.data = data
        self.ack_to = ack_to
        self.timestamp = timestamp
        self.format = '<QLHHHd'
        self.header_size = struct.calcsize(self.format)
        if data is not None:
            self.packed_size = len(data) + self.header_size
        else:
            self.packed_size = 0
                #print("Created %s" % str(self))

    def __str__(self):
        return 'BlockSenderChunk<%u,%u,%u,%u>' % (self.block_id, self.chunk_id, self.size, self.chunk_size)

    def pack(self):
        '''return a linearized representation'''        
        buf = bytes(struct.pack(self.format, self.block_id, self.size, self.chunk_id,
                        self.chunk_size, self.ack_to, self.timestamp))
        buf += bytes(self.data)
        return buf

    def unpack(self, buf):
        '''unpack a linearized representation into the object'''
        (self.block_id, self.size,
         self.chunk_id, self.chunk_size, self.ack_to, self.timestamp) = struct.unpack_from(self.format, buf, offset=0)
        self.data = bytes(buf[self.header_size:])


class BlockSenderBlock:
    '''the state of an incoming or outgoing block'''
    def __init__(self, block_id, size, chunk_size, dest, mss, data=None, callback=None, priority=0):
        self.block_id = block_id
        self.size = size
        self.chunk_size = chunk_size
        self.num_chunks = (self.size + (chunk_size-1)) // chunk_size
        #FIXME mss == where the acks need to go?
        self.acks = BlockSenderSet(block_id, self.num_chunks, mss)
        if data is not None:
            self.data = bytearray(data)
        else: #incoming packet?
            self.data = bytearray(size)#bytearray(size)

        self.data_length = 0
        self.num_chunks_recv = 0    
        
        self.timestamp = 0
        self.callback = callback
        self.dest = dest
        self.next_chunk = 0
        self.priority = priority
        self.sends = 0
        self.chunk_send_times = {}
        #print("Created %s" % str(self))

    def __str__(self):
        return 'BlockSenderBlock<%u,%u,%u,%u>' % (self.block_id,self.size,self.chunk_size,self.num_chunks)

    def chunk(self, chunk_id):
        '''return data for a chunk'''
        start = chunk_id*self.chunk_size
        return self.data[start:start+self.chunk_size]        

    def complete(self):
        '''return true if all chunks have been sent/received'''
        return self.acks.complete()


class BlockSender:
    '''a reliable datagram block sender

    port:          UDP port to listen on, use zero for a system allocated port. This
        port can be queried via get_port()
    dest_ip:       default IP to send to
    dest_port:     default port for send, defaults to port
    listen_ip:     IP to listen on (default is wildcard)
    bandwidth:     bandwidth to use in bytes/second (default 100000 bytes/s)
    completed_len: how many completed blocks to remember (default 100)
    chunk_size:    size of data chunks to send in bytes (default 1000)
    backlog:       maximum number of packets to send per tick (default 100)
    rtt:           initial round trip time estimate (0.01 seconds)
    sock:          a optional socket object to use, needs sendto() and recvfrom()
                plus a fileno() method if recv() with non-zero timeout is used
    mss:           maximum segment size for any packet. This limits all
               packet types (default is zero, meaning no limit)
    ordered:       set to True to force blocks to be delivered in the sending order (default False)
    debug:         enable debugging (default False)
    '''
    def __init__(self, port=0, dest_ip=None, dest_port=None, listen_ip='', bandwidth=100000,
             completed_len=1000, chunk_size=1000, backlog=100, rtt=0.01,
             sock=None, mss=0, ordered=False,
             debug=False, filler = None): ##TO DO... populate section with a filler char on creation
        self.bandwidth = bandwidth
        self.port = port
        if dest_port is None:
            dest_port = port
        if sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((listen_ip, port))
            self.sock.setblocking(False)
            if port == 0:
                (host, self.port) = self.sock.getsockname()
        else:
            self.sock = sock
        self.dest_ip = dest_ip
        self.dest_port = dest_port
        self.outgoing = []
        self.incoming = []
        self.block_status = []
        self.next_block_id = os.getpid() << 20
        self.last_send_time = time.time()
        self.last_recv_time = time.time()
        self.acks_needed = set()
        self.packet_loss = 0
        self.completed_len = completed_len
        self.completed = []
        self.completed2 = []
        if chunk_size > 65535:
            raise BlockSenderException('chunk size must be less than 65536')
        self.chunk_size = chunk_size
        self.enable_debug = debug
        self.backlog = backlog
        self.rtt_estimate = rtt
        self.rtt_max = 5
        self.rtt_multiplier = 3.0
        self.mss = mss
        self.ordered = ordered
        self.bonus_bytes = 0
        self.efficiency = 1.0
        self.bandwidth_used = 0.0
        self.send_count = 0
        self.recv_count = 0

        # work out the overheads of the packet types
        self.chunk_overhead = BlockSenderChunk(0,0,0,'',0,0,0).header_size
        self.ack_overhead = BlockSenderSet(0,0,0).header_size
        if self.mss and (self.mss < self.chunk_overhead + 1 or
                 self.mss < self.ack_overhead + 4):
            raise BlockSenderException('mss is too small')

    def get_port(self):
        '''return the port we are receiving on'''
        return self.port

    def set_dest_port(self, port):
        '''set the port we send to by default'''
        self.dest_port = port

    def set_packet_loss(self, loss):
        '''set a percentage packet loss
        This can be used to simulate lossy networks
        '''
        self.packet_loss = loss

    def set_bandwidth(self, bandwidth):
        '''set the bandwidth on an open sender'''
        self.bandwidth = bandwidth

    def get_efficiency(self):
        '''return the average efficiency of the link. An efficiency of 1.0 means
        each chunk is sent just once. An efficiency of 0.2 means each chunk is
        sent an average of 5 times'''
        return self.efficiency

    def get_rtt_estimate(self):
        '''return an estimate of the round trip time'''
        return self.rtt_estimate

    def get_bandwidth_used(self):
        '''return a moving average of the actual bandwidth used'''
        return self.bandwidth_used

    def send(self, data, dest=None, chunk_size=None, callback=None, priority=0, block_id = None):
        '''send a data block

        dest:       optional (host,port) tuple
        chunk_size: network send size for this block (defaults to self.chunk_size)
        callback:   optional callback function on completion of send (default None)
        priority:   optional priority for sending this packet. Higher priority packets
                    are sent first (default 0)
        block_id:    optional can be set by external program to add block location info (WARNING must be unique!)
        '''
        if not chunk_size:
            chunk_size = self.chunk_size
        if self.mss and chunk_size > self.chunk_overhead + self.mss:
            chunk_size = self.mss - (self.chunk_overhead + PACKET_HEADER_SIZE)

        num_chunks = (len(data) + (chunk_size-1)) // chunk_size
        if num_chunks > 65535:
            raise BlockSenderException('chunk_size of %u is too small for data length %u' % (chunk_size, len(data)))
        if block_id == None:
            block_id = self.next_block_id #use the default block id
        
        self.next_block_id += 1
        if dest is None:
            if self.dest_ip is None:
                raise BlockSenderException('no destination specified in send')
            dest = (self.dest_ip, self.dest_port)
        
        
        ###FIXME define where the block is going? dest = self.dest?
        newblk = BlockSenderBlock(block_id, len(data), chunk_size, dest, self.mss,
                      data=data, callback=callback, priority=priority)

        # if this block has a non-zero priority, insert after the last one with a
        # higher or equal priority
        if priority > 0:
            for i in range(len(self.outgoing), 0, -1):
                if self.outgoing[i-1].priority >= priority:
                                        #print("Inserted blk %u len=%u %s" % (i, len(self.outgoing), newblk))
                    self.outgoing.insert(i, newblk)
                    return
                        #print("Inserted blk %u len=%u %s" % (0, len(self.outgoing), newblk))
            self.outgoing.insert(0, newblk)
            return
        # otherwise append to the outgoing list
                #print("Appended blk len=%u %s" % (len(self.outgoing), newblk))
        self.outgoing.append(newblk)

    def _crc(self, buffer):
        '''produce a 32 bit unsigned crc for a buffer'''
        return binascii.crc32(bytes(buffer)) & 0xFFFFFFFF

    def _debug(self, s):
        '''internal debug function'''
        if self.enable_debug:
            print(s)
        pass

    def _send_object(self, obj, type, dest):
        '''low level object send'''
        if self.packet_loss != 0:
            if random.uniform(0, 1) < self.packet_loss*0.01:
                                #print("lose packet")
                return
        try:
            buf = obj.pack()
            crc = self._crc(buf)
            buf = bytes(struct.pack('<BL', type, crc)) + buf
            #self.sock.sendto(buf, dest)
            self.sock.sendto(buf, (self.dest_ip,self.dest_port))
            ###FIXME HACK this dest is not the correct one... force the use of the specified dest_ip and dest_port
            #print 'sending to', dest
            self.send_count += 1
                        #print("send_count=%u %s" % (self.send_count, obj))
        except socket.error:
            pass

    def _send_acks(self):
        '''send extents objects to acknowledge data'''
        tnow = time.time()
        deltat = tnow - self.last_recv_time
        self.last_recv_time = tnow
        if self.acks_needed and self.enable_debug:
            print("sending %u acks deltat=%.2f" % (len(self.acks_needed), deltat))
        acks_needed = self.acks_needed.copy()
        for obj in acks_needed:
            try:
                if isinstance(obj, BlockSenderBlock):
                    obj.acks.timestamp = obj.timestamp
                    if obj.complete():
                        #FIXME this is acking to the wrong address?
                        #ack = BlockSenderComplete(obj.block_id, obj.timestamp, obj.dest)
                        #self._send_object(ack, PKT_COMPLETE, obj.dest)
                        ack = BlockSenderComplete(obj.block_id, obj.timestamp, (self.dest_ip,self.dest_port))
                        self._send_object(ack, PKT_COMPLETE, (self.dest_ip,self.dest_port))
                    else:
                        pkt = obj.acks
                        #self._send_object(obj.acks, PKT_ACK, obj.dest)
                        self._send_object(obj.acks, PKT_ACK, (self.dest_ip,self.dest_port))
                else:
                    (block_id, dest) = obj
                    #ack = BlockSenderComplete(block_id, time.time(), dest)
                    #self._send_object(ack, PKT_COMPLETE, dest)
                    ack = BlockSenderComplete(block_id, time.time(), (self.dest_ip,self.dest_port))
                    self._send_object(ack, PKT_COMPLETE, (self.dest_ip,self.dest_port))
                    #print 'dest', dest
                    ###FIX ME wrong address? dest 
                self.acks_needed.remove(obj)
            except Exception as e:
                self._debug('_send_acks: ' + str(e))
                return

    def _add_chunk(self, blk, chunk, fill = None):
        '''add an incoming chunk to a block'''
        
        blk.acks.add(chunk.chunk_id, chunk.ack_to)
        start = chunk.chunk_id*chunk.chunk_size
        length = len(chunk.data)
        blk.data_length += length
    
        blk.data[start:start+length] = chunk.data
        
        self.acks_needed.add(blk)

    def _complete_send(self, blk):
        '''complete send of a block'''
        if blk.callback:
                        #print("Callback %s" % blk.callback)
            blk.callback()
        efficiency = blk.num_chunks / float(blk.sends)
        #print("_complete_send: efficiency=%.2f sends=%u recvs=%u" % (efficiency, self.send_count, self.recv_count))
        self.efficiency = 0.95 * self.efficiency + 0.05 * efficiency

    def _check_incoming(self):
        '''check for incoming data or acks. Return True if a packet was received'''
        try:
            (buf, fromaddr) = self.sock.recvfrom(65536)
        except socket.error:
            return False
        if len(buf) == 0:
            return False
        self.recv_count += 1
        if self.dest_ip is None:
            if self.enable_debug:
                self._debug('connection from %s' % str(fromaddr))
            # setup defaults for send based on first connection
            ##FIXME ???
            (self.dest_ip,self.dest_port) = fromaddr
        try:
            if len(buf) < PACKET_HEADER_SIZE:
                self._debug('bad packet %s' % msg)
                return True
            (magic,crc) = struct.unpack_from('<BL', buf)
            remaining = buf[PACKET_HEADER_SIZE:]
            if crc != self._crc(remaining):
                self._debug('bad crc')
                return True                
            if magic == PKT_ACK:
                obj = BlockSenderSet(0,0,0)
                obj.unpack(remaining)
            elif magic == PKT_COMPLETE:
                obj = BlockSenderComplete(0, None, None)
                obj.unpack(remaining)
            elif magic == PKT_CHUNK:
                obj = BlockSenderChunk(0, 0, 0, "", 0, 0, 0)
                obj.unpack(remaining)
            else:
                self._debug('bad magic %u' % magic)
                return True
        except Exception as e:
            self._debug('_check_incoming: bad packet %s' % str(e))
            return True
        tnow = time.time()
                #print(obj)
        if isinstance(obj, BlockSenderSet):
            # we've received a set of acks for some data
            # find the corresponding outgoing block
            self.rtt_estimate = min(self.rtt_max, 0.95 * self.rtt_estimate + 0.05 * (tnow - obj.timestamp))
            for i in range(len(self.outgoing)):
                out = self.outgoing[i]
                if out.block_id == obj.id:
                    if self.enable_debug:
                        self._debug("ack %s %f" % (str(out.acks), tnow - obj.timestamp))
                    out.acks.update(obj)
                    if out.acks.complete():
                        if self.enable_debug:
                            self._debug("send complete %u %s" % (out.block_id, obj))
                        blk = self.outgoing.pop(i)
                        self._complete_send(blk)
                    return True
            # an ack for something already complete
            return True

        if isinstance(obj, BlockSenderComplete):
            # a full block has been received
            if self.enable_debug:
                self._debug("full ack for block_id %u" % obj.block_id)
            self.rtt_estimate = min(self.rtt_max, 0.95 * self.rtt_estimate + 0.05 * (tnow - obj.timestamp))
            for i in range(len(self.outgoing)):
                out = self.outgoing[i]
                if out.block_id == obj.block_id:
                    blk = self.outgoing.pop(i)
                    if self.enable_debug:
                        self._debug("send complete %u outlen=%u %s %s" % (
                                                        out.block_id, len(self.outgoing), obj, blk))
                    self._complete_send(blk)
                    return True
            # an ack for something already complete
            return True

        if isinstance(obj, BlockSenderChunk):
            # we've received a chunk of data
            if obj.block_id in self.completed:
                # we've already completed this block_id
                if self.enable_debug:
                    self._debug("got completed chunk %u of %u" % (obj.chunk_id, obj.block_id))
                self.acks_needed.add((obj.block_id, fromaddr))
                #self.acks_needed.add((obj.block_id, (self.dest_ip,self.dest_port)))
                #FIXME fromaddr
                return True
            for i in range(len(self.incoming)):
                blk = self.incoming[i]
                if blk.block_id == obj.block_id:
                    # we have an existing incoming object
                    if self.enable_debug:
                        if obj.chunk_id in blk.acks.chunks:
                            self._debug("got dup chunk %u of %u" % (obj.chunk_id, obj.block_id))
                        else:
                            self._debug("got chunk %u of %u" % (obj.chunk_id, obj.block_id))
                    blk.timestamp = obj.timestamp
                    self._add_chunk(blk, obj)
                    return True
            # its a new block
            if self.enable_debug:
                self._debug("new block chunk %u of %u (size=%u chunk_size=%u)" % (
                                        obj.chunk_id, obj.block_id, obj.size, obj.chunk_size))
            self.incoming.append(BlockSenderBlock(obj.block_id, obj.size, obj.chunk_size, fromaddr, self.mss))
            #self.incoming.append(BlockSenderBlock(obj.block_id, obj.size, obj.chunk_size, (self.dest_ip,self.dest_port), self.mss))
            #FIXME fromaddr?
            #print 'fromaddr',fromaddr
            blk = self.incoming[-1]
            blk.timestamp = obj.timestamp
            self._add_chunk(blk, obj)
            return True
        self._debug("unexpected incoming packet type")
        return True


    def available(self, ordered=None):
        '''return the first incoming block if completed or None

        This does no network operations
        '''
        if ordered is None:
            ordered = self.ordered
        imax = len(self.incoming)
        if ordered:
            imax = min(1, imax)
        for i in range(imax):
            if self.incoming[i].complete():
                blk = self.incoming.pop(i)
                print("available sends=%u recvs=%u" % (self.send_count, self.recv_count))
                self.completed.append(blk.block_id)
                self.completed2.append((blk.block_id, blk.data))
                #add completed block call back here
                #fixme
                while len(self.completed) > self.completed_len:
                    self.completed.pop(0)        
                return blk.data
        return None

    def report(self, detailed=False):
        '''report chunk status'''
        total_acked = 0
        total_chunks = 0
        for i in range(len(self.outgoing)):
            blk = self.outgoing[i]
            total_acked += len(blk.acks.chunks)
            total_chunks += blk.acks.num_chunks
            if detailed:
                print("block %u  acked %u/%u" % (blk.block_id, len(blk.acks.chunks), blk.acks.num_chunks))
                print("block %u  acked %f" % (blk.block_id, (float(len(blk.acks.chunks))/float(blk.acks.num_chunks))*100.))                
                complete = "0"
                if len(self.incoming) > 0:
                    complete = "%u/%u" % (len(self.incoming[0].acks.chunks), self.incoming[0].acks.num_chunks)
                    print("total_acked=%u total_chunks=%u eff=%.2f rtt=%.1f bw=%.2f qsize=%u in=%u/%s" % (
                            total_acked, total_chunks, self.get_efficiency(), self.get_rtt_estimate(),
                            self.get_bandwidth_used(),
                            self.sendq_size(), len(self.incoming), complete))
        print ""
                
    def sendq_size(self):
        '''return number of uncompleted blocks in the send queue'''
        return len(self.outgoing)


    def recv(self, timeout=0, ordered=None):
        '''receive next chunk from network. Return data or None

        timeout:  time to wait for a packet (0 means to return immediately)
        ordered:  return blocks in same order as sent (default False)
        '''
        if ordered is None:
            ordered = self.ordered
        data = self.available(ordered=ordered)
        if data is not None:
            return data
        if len(self.incoming) > 0 and self.incoming[0].complete():
            return self.incoming.pop(0).data            
        if timeout != 0:
            rin = [self.sock.fileno()]
            try:
                (rin, win, xin) = select.select(rin, [], [], timeout)
            except select.error:
                return None
        self._check_incoming()
        return self.available(ordered=ordered)


    def reset_timer(self):
        '''reset the timer used for bandwidth control'''
        self.last_send_time = time.time()


    def _send_outgoing(self, max_queue=None):
        '''send any outgoing data that is due to be sent'''
        if len(self.outgoing) == 0:
            return

        tnow = time.time()
        deltat = tnow - self.last_send_time
        bytes_to_send = int(self.bandwidth * deltat)
        if bytes_to_send <= 0:
            return
        bytes_sent = 0
        chunks_sent = 0

        # we can get bonus bytes to send from the previous tick, due to the granularity of
        # the chunk size
        bytes_to_send += min(self.bonus_bytes, self.chunk_size)

        count = len(self.outgoing)
        if max_queue is not None:
            count = min(max_queue, count)

        for i in range(count):
            blk = self.outgoing[i]

            # in order to preserve ordering, we have to make sure the other end
            # has acked at least one chunk from the previous block before moving
            # to the next block
            if self.ordered and i > 0 and not self.outgoing[i-1].acks.started():
                break

            # start where we left off
            chunks = list(range(blk.next_chunk, blk.num_chunks))
            chunks.extend(range(blk.next_chunk))
    
            for c in chunks:
                
                if blk.acks.present(c):
                    # we've received an ack for this chunk already
                    continue
                if bytes_sent + blk.chunk_size > bytes_to_send:
                    # this would take us over our bandwidth limit
                    break
                if c in blk.chunk_send_times:
                    if tnow - blk.chunk_send_times[c] < self.rtt_multiplier*self.rtt_estimate:
                        # wait for a possible ack
                        continue

                chunk = BlockSenderChunk(blk.block_id, blk.size, c, blk.chunk(c),
                             blk.chunk_size, blk.acks.first_missing, tnow)
                

                if bytes_sent + chunk.packed_size > bytes_to_send:
                    # this would take us over our bandwidth limit
                    break

                try:
                    self._send_object(chunk, PKT_CHUNK, blk.dest)
                except Exception as e:
                    self._debug('_send_outgoing: ' + str(e))
                    break
                                #print("sent chunk size=%u of %u sends=%u block_id=%u" % (
                                #        chunk.chunk_size, blk.size, blk.sends, blk.block_id))
                bytes_sent += chunk.packed_size
                blk.next_chunk = (c + 1) % blk.num_chunks
                blk.timestamp = tnow
                blk.sends += 1
                chunks_sent += 1
                blk.chunk_send_times[c] = tnow
                if chunks_sent == self.backlog:
                    # don't send more than self.backlog per tick
                    break

        self.bonus_bytes = bytes_to_send - bytes_sent
        if bytes_sent != 0:
            self.bandwidth_used = 0.99 * self.bandwidth_used + 0.01 * (bytes_sent/deltat)
            self.last_send_time = tnow


    def tick(self, packet_count=None, send_acks=True, send_outgoing=True, max_queue=None):
        '''periodic timer to trigger data sends

        This should be called regularly to process incoming packets, send acks and send any
        pending data

        packet_count:  maximum number of incoming packets to process (default self.backlog)
        send_acks:     send acknowledgement packets (default True)
        send_outgoing: send outgoing packets (default True)
        '''
        # check for incoming packets
        if packet_count is None:
            packet_count = self.backlog
        for i in range(packet_count):
            if not self._check_incoming():
                break

        # send any acks that are needed
        if send_acks:
            self._send_acks()

        # send outgoing data
        if send_outgoing:
            self._send_outgoing(max_queue=max_queue)
