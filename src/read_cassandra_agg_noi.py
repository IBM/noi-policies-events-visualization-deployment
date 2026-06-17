#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
'''
Read Cassandra Aggregation Data
Utility for reading aggregated data from Cassandra
'''
'''
Author: Yasser Abduallah 
'''

import json
import os 
from datetime import *

from cassandra.query import SimpleStatement
import datetime 
import argparse
from mime_cassandra_util import *

#gets the current location of the script
script_location = os.path.dirname(os.path.realpath(__file__))

#static variables:
ssl_message = "An SSL configuration file to connect to Cassandra with the details SSL connection information in a the configuration."


ssl_config_params = {'CASSANDRA_USERNAME':'cassandra',
                     'CASSANDRA_PASSWORD':'********',
                     'CASSANDRA_HOSTNAME':'localhost',
                     'CASSANDRA_PORT': '9042',
                     'CASSANDRA_CA_LOCATION':'',
                     'CASSANDRA_PROTOCOL':'TLSv1.2',
                     'CASSANDRA_DATACENTER':'datacenter1',
                     'PROTOCOL_VERSION':'4'}


class CassandraAlertsAgg:
    '''
    This program is a utility to provide some information about the tables in cassandra.
    It uses the current cassandra connection from MIME framework. It reads the data in batches.
    python3 read_cassandra_agg_noi.py -h 
    will show the available options that can be used.

    Attributes
    ----------
    batch_size: int
        The number of rows to select when reading the table. Default is 100000

    threshold: int
        The number to use as an interval to show the progress. Default is 10000

    debug_time: bool
        Show the time each batch takes while reading the table. Default is True

    includedetails: bool
        Finds the number of alerts without details in the payload. Default is False

    countdetailskeys: bool
        Counts the number of alerts that includes only 1 key. Default is False.
        Note. this option requires --includedetails to be true

    ssl_config: str
        An SSL configuration file to connect to cassandra with the details SSL connection information in a the configuration. Default is blank.

    print_ssl_config: bool
        Shows an example of the SSL configuration file.  Default is False.

    Methods
    -------
    parse_input_parameters -> void
        parses the command line user input parameters.
    
    get_boolean -> bool
        convers the input value into a boolean value.
    
    set_ssl_config -> void
        Sets the SSL configuration that is provided in the config_file.
    
    
    start_Processing -> void
        Starts the process by checking parameters to print message or continue.
    
    get_table_aggs -> void
        runs the queries and prints the end result.
        
    '''

    def __init__(self, args=None) -> None:
        '''
            initialization method
        '''
        if args is not None:
            self.parse_input_parameters(args)
        

    def parse_input_parameters(self, args) -> None:
        self.batchsize = args.get('batch_size')
        self.threshold = args.get('threshold')
        self.debug_time = self.get_boolean(args.get('debug_time'))
        self.countdetailskeys = self.get_boolean(args.get('countdetailskeys'))
        self.print_ssl_config = self.get_boolean(args.get('print_ssl_config'))
        self.includedetails = self.get_boolean(args.get('includedetails'))   
        self.ssl_config = args.get('ssl_config')
        self.filter = args.get('filter')
        self.limit = args.get('limit')
        
    def get_boolean(self,v) -> bool:
        '''
        convers the input value into a boolean value.
        v = "true"
        result = get_boolean(v)

        print(result) 

        True
        '''
        v = str(v).strip().lower()
        return v  == "true"

    def set_ssl_config(self, config_file):
        '''
        Sets the SSL configuration that is provided in the config_file.

        It uses the function defention from the mime_cassandra_utils
        '''
        config_file = str(config_file).strip()
        handler = open(config_file,'r')
        props = {}
        for p in handler:
            p = str(p).strip()
            if p != '' and not p.startswith('#') and '=' in p:
                index = p.index('=')
                key = str(p[:index]).strip()
                val = str(p[index+1:]).strip()
                if key != '' and val != '':
                    props[key] = val 
        if len(props) == 0:
            print('\nError: The ssl config file does not include any properties:', config_file,'\n')
            exit()
        else:
            if 'CASSANDRA_USERNAME' in props.keys():
                set_username(props['CASSANDRA_USERNAME'])
            if 'CASSANDRA_PASSWORD' in props.keys():
                set_password(props['CASSANDRA_PASSWORD'])
            if 'CASSANDRA_HOSTNAME' in props.keys():
                set_host(props['CASSANDRA_HOSTNAME'])
            if 'CASSANDRA_PORT' in props.keys():
                set_port(props['CASSANDRA_PORT'])            
            if 'CASSANDRA_PROTOCOL' in props.keys():
                set_protocol(props['CASSANDRA_PROTOCOL'])   
            if 'CASSANDRA_DATACENTER' in props.keys():
                set_datacenter(props['CASSANDRA_DATACENTER'])         
            if 'PROTOCOL_VERSION' in props.keys():
                set_protocol_version(props['PROTOCOL_VERSION'])               
            if 'CASSANDRA_CA_LOCATION' in props.keys():
                if not os.path.exists(props['CASSANDRA_CA_LOCATION']):
                    print('SSL ca certificate location does not exist:', props['CASSANDRA_CA_LOCATION'])
                    exit()
                set_ca_location(props['CASSANDRA_CA_LOCATION'])                            

    def start_Processing(self)-> None:
        '''
        Starts the process by checking parameters to print message or continue
        '''
        if self.print_ssl_config:
            print('The SSL configuration file should contain:')
            for config_param in ssl_config_params:
                if 'PASS' in config_param.upper():
                    print(config_param, '= << default value:XXXXXX >>')
                else:
                    print(config_param, '= << default value:',ssl_config_params[config_param],'>>')
            exit()

        if self.ssl_config is not None:
            if not os.path.exists(self.ssl_config):
                file_name = self.ssl_config
                print('The configuration file does not exist:', file_name)
                print('Make sure to provide the full path to the configuration file.')
                exit()
            else:
                self.set_ssl_config(self.ssl_config)

        self.get_table_aggs()

    def get_table_aggs(self) -> None:
        '''
        runs the queries and prints the end result.
        '''
        print('Loading data with batch size:', self.batchsize, ' and threshold:', self.threshold, 'and debug_time:', self.debug_time)

        startingTime = datetime.datetime.now()
            
        session = get_cassandra_session()
        counter = 0
        query = 'select payload, hourkey,"timestamp", event_id,severity from ea_events.events '
        if self.includedetails:
            answer=input('!! Minor warning:\nIncluding the details in the payload column might be slow process. You may want to set the cluster with larger client timeout.\nDo you want to continue?[y] ')
            answer = str(answer).lower()
            if not answer in ['yes','y','ok','']:
                print('Exiting..')
                exit()
            query = 'select payload, hourkey,"timestamp", event_id,severity from ea_events.events '
        
        filter = self.filter
        isFilterIncluded = False
        if filter is not None and str(filter).strip() != '':
            filter = str(filter).strip()
            print('Adding filter')
            if 'ALLOW FILTERING' in filter.upper():
                index = filter.upper().index('ALLOW FILTERING')
                filter = filter[:index]
            query = query + '  WHERE ' + filter
            isFilterIncluded = True
        
        limit = self.limit 
        if limit is not None and int(float(limit)) > 0:
            query = query + ' LIMIT ' + str(int(float(limit)))
        
        if isFilterIncluded:
            query = query + ' ALLOW FILTERING'

        print('The query to send to cassandra with batches:', query)


        maxfc = datetime.datetime(MINYEAR+1,1,1,0,0)
        minfc = datetime.datetime(MAXYEAR,1,1,0,0)
        maxdk =  maxfc.timestamp() * 1000
        mindk = minfc.timestamp() * 1000

        numResolutionAlerts = 0
        numProblemAlerts = 0
        numEmptyEvent_id = 0
        numEmptyTypes = 0
        numOtherTypes = 0
        numNoDetails = 0
        oneKeyDetailsCount=0

        startingBatchTime=startingTime
        totalTimeCounter = datetime.timedelta(days=0)

        print('Getting count, max, min timestamps and more...')

        statement = SimpleStatement(query, fetch_size=self.batchsize)
        for row in session.execute(statement):
            counter = counter + 1 
            fc = row.timestamp
            if fc > maxfc:
                maxfc = fc 
            if fc < minfc:
                minfc = fc 
            try:
                dk = float(str(row.hourkey))
                if dk > maxdk:
                    maxdk = dk
                if dk < mindk:
                    mindk = dk
            except Exception as e:
                dayValue = row.hourkey
                print('Unable to process row for day value ', dayValue , " but will continue anyway..")
            if counter % self.threshold == 0:
                if self.debug_time:
                    timeDif = datetime.datetime.now() - startingBatchTime
                    totalTimeCounter = totalTimeCounter + timeDif
                    print(f"Processed  {counter:,} rows -- time: {timeDif}   total time: {totalTimeCounter}")
                    startingBatchTime=datetime.datetime.now()
                else:
                    print(f"Processed  {counter:,}  rows")
            sigature = str(row.event_id).strip()
            if sigature == '':
                numEmptyEvent_id = numEmptyEvent_id + 1

            alertType = json.loads(row.payload)['resolution']
            if alertType == '':
                numEmptyTypes = numEmptyTypes + 1
            else:
                try:
                    #don't parse the type to save time in processing
                    if not alertType:
                        numProblemAlerts = numProblemAlerts + 1
                    else:
                        numResolutionAlerts = numResolutionAlerts + 1
                except Exception as e :
                    print('Unable to process type as json, will continue:', alertType, e)
            if self.includedetails: 
                if not 'details' in row.payload:
                    numNoDetails = numNoDetails + 1
                else:
                    if self.countdetailskeys:
                        payload=json.loads(row.payload)
                        detailsKeys = payload['details'].keys()
                        if len(detailsKeys) == 1: 
                            oneKeyDetailsCount = oneKeyDetailsCount + 1    



        print(f'Total number of alerts          : {counter:,}')
        print(f'Min FirstOccurrence             :', minfc)
        print(f'Max FirstOccurrence             :', maxfc)
        print(f'Min hourkey                      :', int(mindk))
        print(f'Max hourkey                      :', int(maxdk))
        print(f'Number of problem alerts        : {numProblemAlerts:,}')
        print(f'Number of resolution alerts     : {numResolutionAlerts:,}')
        print(f'Number of other types alerts    : {numOtherTypes:,}')
        print(f'Number of empty event_id        : {numEmptyEvent_id:,}')
        print('Total time to get the aggregates:', (datetime.datetime.now() - startingTime))
	

if __name__ == "__main__":
    #check if the user provided any input parameters. 
    parser = argparse.ArgumentParser(
                        prog='read_cassandra_agg',
                        description='Read the ea_events.events table to get the count, max and min timestamp, and other statistics about the data.',
                        epilog='') 
    parser.add_argument('-b', '--batch_size',
                        default=100000, type=int, help='The number of rows to select when reading the table.')  

    parser.add_argument('-t', '--threshold',
                        default=10000, type=int, help='The number to use as an interval to show the progress.')  

    parser.add_argument('-d', '--debug_time',
                        default="True", type=str, help='Show the time each batch takes while reading the table.') 
    

    parser.add_argument('-i', '--includedetails', 
                        default="False",type=str, help='Finds the number of alerts without details in the payload.')  

    parser.add_argument('-k', '--countdetailskeys', 
                        default="False",type=str, help='Counts the number of alerts that includes only 1 key. Note. this option requires --includedetails to be true') 

    parser.add_argument('-ssl', '--ssl_config', 
                        default=None,type=str, help=ssl_message)      

    parser.add_argument('-p', '--print_ssl_config', 
                        default="False",type=str, help="Shows an example of the SSL configuration file.")
    
    parser.add_argument('-f', '--filter',
                        default=None,type=str,help="Provide a filter to use with the query. Make sure ALLOW FILTERING is not included in the filter, it will be added by default." )

    parser.add_argument('-l', '--limit',
                        default=None,type=int,help="Provide a number of rows to limit the returned result from the query. Must be > 0" )
      
     

    args=parser.parse_args()
    args = vars(args)

    obj = CassandraAlertsAgg(args)
    try:
        obj.start_Processing()
    except Exception as e:
        print('Unable to run the the process to get aggregates from the table', e)
    try:
        shutdown_session()
    except Exception as e:
        print('Unable to shutdown cassandra session, exiting',e)
        exit(1)
