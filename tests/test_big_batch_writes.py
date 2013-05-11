import uuid
import thrift
import getpass
import logging
logger = logging.getLogger('test')
logger.setLevel( logging.INFO)

ch = logging.StreamHandler()
ch.setLevel( logging.DEBUG )
formatter = logging.Formatter('%(asctime)s %(process)d:%(lineno)d: %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

## get the Cassandra client library
import pycassa
from pycassa.pool import ConnectionPool
from pycassa.system_manager import SystemManager, SIMPLE_STRATEGY, \
    LEXICAL_UUID_TYPE, ASCII_TYPE, BYTES_TYPE

log = pycassa.PycassaLogger()
log.set_logger_name('pycassa_library')
log.set_logger_level('debug')
log.get_logger().addHandler(logging.StreamHandler())

class Listener(object):
    def connection_failed(self, dic):
        logger.critical('connection_failed: reset pool??')

def test_big_batched_writes():
    ## this is an m1.xlarge doing nothing but supporting this test
    server = 'localhost:9160'
    keyspace = 'testkeyspace_' + getpass.getuser().replace('-', '_')
    family = 'testcf'
    sm = SystemManager(server)
    try:
        sm.drop_keyspace(keyspace)
    except pycassa.InvalidRequestException:
        pass
    sm.create_keyspace(keyspace, SIMPLE_STRATEGY, {'replication_factor': '1'})
    sm.create_column_family(keyspace, family, super=False,
                            key_validation_class = LEXICAL_UUID_TYPE,
                            default_validation_class  = LEXICAL_UUID_TYPE,
                            column_name_class = ASCII_TYPE)
    sm.alter_column(keyspace, family, 'test', ASCII_TYPE)
    sm.close()

    pool = ConnectionPool(keyspace, [server], max_retries=10, pool_timeout=0, pool_size=10, timeout=120)
    pool.fill()
    pool.add_listener( Listener() )

    ## assert that we are using framed transport
    conn = pool._q.get()
    assert isinstance(conn.transport, thrift.transport.TTransport.TFramedTransport)
    pool._q.put(conn)

    try:
        for num_rows in range(14, 20):
            ## write some data to cassandra using increasing data sizes
            one_mb = ' ' * 2**20
            rows = []
            for i in xrange(num_rows):
                key = uuid.uuid4()
                rows.append((key, dict(test=one_mb)))

            testcf = pycassa.ColumnFamily(pool, family)
            with testcf.batch() as batch:
                for (key, data_dict) in rows:
                    data_size = len(data_dict.values()[0])
                    logger.critical('adding %r with %.6f MB' % (key, float(data_size)/2**20))
                    batch.insert(key, data_dict)

            logger.critical('%d rows written' % num_rows)

    finally:
        sm = SystemManager(server)
        try:
            sm.drop_keyspace(keyspace)
        except pycassa.InvalidRequestException:
            pass
        sm.close()
        logger.critical('clearing test keyspace: %r' % keyspace)
