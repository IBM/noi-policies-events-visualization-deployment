#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
'''
MIME Cassandra Utility
Utility functions for interacting with Cassandra database
'''

import os
import ssl
from cassandra.cluster import ExecutionProfile, Cluster, EXEC_PROFILE_DEFAULT, PlainTextAuthProvider, DCAwareRoundRobinPolicy
from cassandra.query import SimpleStatement
from time import sleep, time

host = os.getenv('CASSANDRA_HOST', 'localhost')
port = os.getenv('CASSANDRA_PORT', 9042)
port = int(port)
protocol = os.getenv('CASSANDRA_PROTOCOL', '')
ca_location = os.getenv('CASSANDRA_CA_LOCATION', '')
username = os.getenv('CASSANDRA_CLIENT_USERNAME', 'cassandra')
password = os.getenv('CASSANDRA_CLIENT_PASSWORD', 'cassandra')
key_space = os.getenv('MIME_CONFIG_KEYSPACE', 'mime_config')
models_table = os.getenv('MIME_MODEL_TABLE_NAME', 'models')
models_training_data_table = os.getenv('MIME_MODEL_DATA_TABLE_NAME', 'models_training_data ')
protocol_version = os.getenv('PROTOCOL_VERSION', 4)
config_file = os.getenv('CONFIG_FILE', 'schemas/cassandra/mime_config.cql')
# Enhanced execution profile with better timeout and retry settings for large datasets
profile = ExecutionProfile(
    request_timeout=300000,  # 5 minutes timeout
    retry_policy=None,  # Will be set in get_cassandra_session
    load_balancing_policy=None  # Will be set in get_cassandra_session
)

# Configurable batch sizes for different operations
batch_max_size = int(os.getenv('BATCH_MAX_SIZE', 614000))
policy_batch_size = int(os.getenv('POLICY_BATCH_SIZE', 10000))
event_batch_size = int(os.getenv('EVENT_BATCH_SIZE', 50000))
policy_batch_size = int(os.getenv('POLICY_BATCH_SIZE', 5000))
event_batch_size = int(os.getenv('EVENT_BATCH_SIZE', 2000))

# Sharding configuration
enable_sharding = str(os.getenv('ENABLE_SHARDING', 'False')).lower() in ['true', 'yes', '1']
shard_count = int(os.getenv('SHARD_COUNT', 10))
current_shard = int(os.getenv('CURRENT_SHARD', 0))

# Session management
session = None
sessions = {}  # For multiple sessions when sharding
app_status_table = str(os.getenv('MIME_APP_STATUS_TABLE', 'instance_app_status')).strip()
datacenter = os.getenv('CASSANDRA_LOCALDATACENTER', None)

# Memory management settings
memory_limit_percent = float(os.getenv('MEMORY_LIMIT_PERCENT', 80.0))

if 'CASSANDRA_CLIENT_USERNAME_PATH' in os.environ:
    cassandra_client_username_path=os.getenv('CASSANDRA_CLIENT_USERNAME_PATH')
    print('Setting username from cassandra username path file:', cassandra_client_username_path )
    if cassandra_client_username_path is None or not os.path.exists(cassandra_client_username_path):
        print('Error: Cassandra client username path is invalid:', cassandra_client_username_path, ', will use default username setting.')
    else :
        handler=open(cassandra_client_username_path,'r')
        for line in handler:
            username = line.strip()
            break
        
if 'CASSANDRA_CLIENT_PASSWORD_PATH' in os.environ:
    cassandra_client_password_path = os.getenv('CASSANDRA_CLIENT_PASSWORD_PATH')
    print('Setting password from cassandra password path file:', cassandra_client_password_path)
    if cassandra_client_password_path is None or not os.path.exists(cassandra_client_password_path):
        print('Error: Cassandra client password path is invalid:', cassandra_client_password_path, ', will use default password setting.')
    else :
        handler=open(cassandra_client_password_path,'r')
        for line in handler:
            password = line.strip()
            break

mtls_enabled = str(os.getenv('ENABLE_MTLS', 'False')).strip()
if mtls_enabled.lower().strip() in ['true', 't', 'yes', 'y', '1']:
    mtls_enabled = True
else:
    mtls_enabled = False

if mtls_enabled:
    keystore_location = str(os.getenv('KEYSTORE_LOCATION', '')).strip()
    cert_name = str(os.getenv('CERT_NAME','clientCertificate')).strip()
    client_certificate = str(os.getenv('CLIENT_CERTIFICATE',''))
    client_key = str(os.getenv('CLIENT_KEY',''))

    # mTLS configuration is set
    
    


def set_host(host_arg = None):
    if host_arg and host_arg.strip():
        global host
        host = host_arg


def set_port(port_arg = None):
    if port_arg and port_arg != 0:
        global port
        port = int(port_arg)


def set_protocol(protocol_arg = None):
    if protocol_arg and protocol_arg.strip():
        global protocol
        protocol = protocol_arg


def set_ca_location(ca_location_arg = None):
    if ca_location_arg and ca_location_arg.strip():
        global ca_location
        ca_location = ca_location_arg


def set_username(username_arg = None):
    if username_arg and username_arg.strip():
        global username
        username = username_arg


def set_password(password_arg = None):
    if password_arg and password_arg.strip():
        global password
        password = password_arg


def set_key_space(key_space_arg = None):
    if key_space_arg and key_space_arg.strip():
        global key_space
        key_space = key_space_arg


def set_models_table(models_table_arg = None):
    if models_table_arg and models_table_arg.strip():
        global models_table
        models_table = models_table_arg


def set_models_data_table(models_data_table_arg = None):
    if models_data_table_arg and models_data_table_arg.strip():
        global models_training_data_table
        models_training_data_table = models_data_table_arg


def set_config_file(mconfig_file_arg = None):
    if mconfig_file_arg and mconfig_file_arg.strip():
        global config_file
        config_file = mconfig_file_arg


def set_protocol_version(protocol_version_arg = None):
    if protocol_version_arg and protocol_version_arg.strip():
        global protocol_version
        protocol_version = int(protocol_version_arg)


def set_batch_max_size(batch_max_size_arg = None):
    global batch_max_size

    if not batch_max_size_arg or batch_max_size_arg.strip() == "" or float(batch_max_size_arg) <= 0:
        batch_max_size = 614000
    else:
        batch_max_size = int(batch_max_size_arg)

def set_datacenter(datacenter_name = None):
    global datacenter
    if datacenter_name and datacenter_name.strip() != '':
        datacenter = datacenter_name.strip()

def init_cassandra_parameters(args):
    set_port(args['port'])
    set_host(args['host'])
    set_protocol(args['protocol'])
    set_ca_location(args['calocation'])
    set_username(args['username'])
    set_password(args['password'])
    set_key_space(args['key_space'])
    set_models_table(args['models_table'])
    set_config_file(args['config_file'])
    set_batch_max_size(args['batch_max_size'])
    set_protocol_version(args['protocol_version'])
    set_datacenter(args['datacenter'])


def get_cassandra_session(shard_id=None):
    """
    Get a Cassandra session, optionally for a specific shard
    
    Args:
        shard_id: Optional shard ID to connect to. If None, uses current_shard or no sharding.
    
    Returns:
        A Cassandra session
    """
    global session, sessions

    # Get the latest values from environment variables to ensure we have the most current settings
    datacenter = os.getenv('CASSANDRA_LOCALDATACENTER', None)
    
    # Determine which shard to use
    target_shard = shard_id if shard_id is not None else current_shard
    
    # If sharding is disabled, use the main session
    if not enable_sharding:
        if session is None or session.is_shutdown:
            session = _create_new_session(datacenter)
        return session
    
    # For sharding, use the sessions dictionary
    session_key = f"shard_{target_shard}"
    if session_key not in sessions or sessions[session_key].is_shutdown:
        print(f"Creating new session for shard {target_shard}")
        sessions[session_key] = _create_new_session(datacenter)
    
    return sessions[session_key]

def _create_new_session(datacenter=None):
    """
    Create a new Cassandra session with optimized settings for large datasets
    
    Args:
        datacenter: Optional datacenter name for load balancing
        
    Returns:
        A new Cassandra session
    """
    from cassandra import ConsistencyLevel
    from cassandra.policies import RetryPolicy, TokenAwarePolicy, ConstantReconnectionPolicy
    
    # Configure load balancing policy
    if datacenter and datacenter.strip() != '':
        print('Adding datacenter to the connection: {}'.format(datacenter))
        base_policy = DCAwareRoundRobinPolicy(local_dc=datacenter)
        # Use TokenAwarePolicy for better routing with large datasets
        profile.load_balancing_policy = TokenAwarePolicy(base_policy)
    
    # Configure retry policy for large operations
    class ExtendedRetryPolicy(RetryPolicy):
        def on_read_timeout(self, *args, **kwargs):
            return self.RETRY, ConsistencyLevel.ONE
        def on_write_timeout(self, *args, **kwargs):
            return self.RETRY, ConsistencyLevel.ONE
        def on_unavailable(self, *args, **kwargs):
            return self.RETRY_NEXT_HOST, None
    
    profile.retry_policy = ExtendedRetryPolicy()
    
    # Get connection details
    host = os.getenv('CASSANDRA_HOST', 'localhost')
    host = host.strip().split(',')
    host = [h.strip() for h in host]
    print('Connecting to Cassandra: host = {}, port = {} and user_name = {} and datacenter = {}'.format(
        host, port, username, datacenter))

    # Ensure port is an integer
    port_int = int(port) if port else 9042
    
    # Create cluster with optimized settings for large datasets
    cluster = Cluster(
        host,
        port=port_int,
        protocol_version=int(protocol_version),
        allow_beta_protocol_version=False,
        ssl_context=get_cassandra_ssl_context(),
        execution_profiles={EXEC_PROFILE_DEFAULT: profile},
        reconnection_policy=ConstantReconnectionPolicy(delay=2.0),
        control_connection_timeout=20,
        connect_timeout=20
    )

    if username and not username.strip() == '' and password and not password.strip() == '':
        print('authenticating cluster with user_name and password')
        cluster.auth_provider = PlainTextAuthProvider(username=username, password=password)
    
    # Connect with optimized session settings
    session = cluster.connect()
    
    # Set session to use prepared statements cache
    session.default_fetch_size = 1000  # Smaller fetch size for better memory management
    
    return session


def get_cassandra_ssl_context():
    if not protocol or not ca_location:
        print('TLS not configured')
        return None

    sslprotocol = getattr(ssl, 'PROTOCOL_' + protocol.replace('.', '_'), None)
    if not sslprotocol:
        print('TLS protocol "{}" not valid'.format(protocol))
        return None

    print('Setting up context for {} and {}'.format(sslprotocol, ca_location))
    ssl_context = ssl.SSLContext(sslprotocol)
    ssl_context.load_verify_locations(cafile=ca_location)
    
    if mtls_enabled:
        print("MTLS enabled, loading key store")
        if client_certificate is None or not os.path.exists(client_certificate):
            print("MTLS is enabled, but client certificate file/location does not exist: " + client_certificate)
        if client_key is None or not os.path.exists(client_key):
            print("MTLS is enabled, but client key file/location does not exist: " + client_key)
        #load it anyway so that cassandra fails with an error serviced to the user.
        ssl_context.load_cert_chain(client_certificate, client_key)
    ssl_context.verify_mode = ssl.CERT_REQUIRED

    return ssl_context


def shutdown_session():
    """Shutdown all Cassandra sessions"""
    global session, sessions
    
    # Shutdown main session if it exists
    if session is not None and not session.is_shutdown:
        print("Shutting down main Cassandra session")
        session.shutdown()
    
    # Shutdown all shard sessions
    for shard_id, shard_session in sessions.items():
        if not shard_session.is_shutdown:
            print(f"Shutting down Cassandra session for {shard_id}")
            shard_session.shutdown()
    
    # Clear sessions dictionary
    sessions = {}

def execute_retry_query(query, shard_id=None):
    """
    Execute a query with retry logic, optionally on a specific shard
    
    Args:
        query: The query to execute
        shard_id: Optional shard ID to use for the query
        
    Returns:
        Query result
    """
    retry_count = int(float(str(os.getenv('CASSANDRA_CONNECTION_RETRY_COUNT', '10')).strip()))
    retry_time_init = int(float(str(os.getenv('CASSANDRA_CONNECTION_RETRY_SLEEP_TIME', '2')).strip()))
    
    retry_time = retry_time_init
    result_from_query = None
    
    for retry_index in range(retry_count):
        try:
            # Use the shard-aware session getter
            result_from_query = get_cassandra_session(shard_id).execute(query)
            return result_from_query  # Return immediately on success
        except Exception as e:
            print('Retry count:', retry_index, 'out of', retry_count, ', unable to execute query:', query)
            print('Error:', e)
            if retry_index >= (retry_count-1):
                print('\n\nError: Unable to connect to Cassandra or execute the configuration query statement after retrying:',
                      retry_count,' and max wait time:', retry_time, ', initial sleep time is set to:', retry_time_init)
                print('Please make sure Cassandra is responsive.')
                print('In addition, you may try to increase the retry count by setting the variable CASSANDRA_CONNECTION_RETRY_COUNT and or initial sleep time variable: CASSANDRA_CONNECTION_RETRY_SLEEP_TIME\n\n')
                exit(1)
            print('Will retry after sleeping for:', retry_time, 'seconds')
            sleep(retry_time)
            print('Awake to retry...')
            retry_time *= 2
    
    return result_from_query  # This should never be reached due to exit(1) above, but added for completeness

def execute_sharded_query(query_template, parameter_sets=None, consistency_level=None):
    """
    Execute a query across all shards and combine results
    
    Args:
        query_template: Query template with parameter placeholders
        parameter_sets: List of parameter sets to use with the query
        consistency_level: Optional consistency level to use
        
    Returns:
        Combined results from all shards
    """
    if not enable_sharding:
        # If sharding is disabled, just execute on the main session
        if parameter_sets:
            return get_cassandra_session().execute(query_template, parameter_sets[0])
        else:
            return get_cassandra_session().execute(query_template)
    
    # Execute across all shards and combine results
    all_results = []
    
    for shard in range(shard_count):
        try:
            session = get_cassandra_session(shard)
            
            # Apply consistency level if provided
            if consistency_level:
                from cassandra import ConsistencyLevel
                query = SimpleStatement(
                    query_template,
                    consistency_level=getattr(ConsistencyLevel, consistency_level)
                )
            else:
                query = query_template
                
            # Execute with parameters if provided
            if parameter_sets and shard < len(parameter_sets):
                results = session.execute(query, parameter_sets[shard])
            else:
                results = session.execute(query)
                
            # Add results to combined list
            all_results.extend(list(results))
            
        except Exception as e:
            print(f"Error executing query on shard {shard}: {e}")
    
    return all_results

def execute_parallel_query(query, parameter_sets, max_workers=5):
    """
    Execute a query in parallel across multiple parameter sets
    
    Args:
        query: Query template with parameter placeholders
        parameter_sets: List of parameter sets to use with the query
        max_workers: Maximum number of parallel workers
        
    Returns:
        Combined results from all queries
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    
    # Track memory usage to avoid OOM errors
    def check_memory_usage():
        try:
            import psutil
            process = psutil.Process()
            memory_percent = process.memory_percent()
            return memory_percent > memory_limit_percent
        except ImportError:
            return False
    
    # Thread-local storage for sessions
    thread_local = threading.local()
    
    def get_thread_session():
        if not hasattr(thread_local, "session"):
            thread_local.session = get_cassandra_session()
        return thread_local.session
    
    # Worker function
    def execute_one(params):
        try:
            session = get_thread_session()
            return list(session.execute(query, params))
        except Exception as e:
            print(f"Error executing query with params {params}: {e}")
            return []
    
    all_results = []
    
    # Adjust worker count based on parameter set size
    actual_workers = min(max_workers, len(parameter_sets))
    
    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        futures = []
        
        # Submit all tasks
        for params in parameter_sets:
            futures.append(executor.submit(execute_one, params))
            
            # Check memory usage periodically
            if len(futures) % 10 == 0 and check_memory_usage():
                print("High memory usage detected, waiting for some queries to complete...")
                # Wait for some futures to complete before submitting more
                for f in as_completed(futures[:10]):
                    all_results.extend(f.result())
                futures = futures[10:]
        
        # Collect all results
        for future in as_completed(futures):
            all_results.extend(future.result())
    
    return all_results
