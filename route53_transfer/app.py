from __future__ import print_function

import csv, sys, time
from datetime import datetime
import itertools
from os import environ
from boto import route53
from boto import connect_s3
from boto.route53.record import Record, ResourceRecordSets
from boto.s3.key import Key

ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", datetime.utcnow().utctimetuple())


class ComparableRecord(object):
    def __init__(self, obj):
        for k, v in obj.__dict__.items():
            self.__dict__[k] = v

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __hash__(self):
        it = (self.name, self.type, self.alias_hosted_zone_id,
              self.alias_dns_name, tuple(sorted(self.resource_records)),
              self.ttl, self.region, self.weight, self.identifier,
              self.failover, self.alias_evaluate_target_health)
        return it.__hash__()

    def to_change_dict(self):
        data = {}
        for k, v in self.__dict__.items():
            if k == 'resource_records':
                continue
            else:
                data[k] = v
        return data


def exit_with_error(error):
    sys.stderr.write(error)
    sys.exit(1)


def get_aws_credentials(params):
    access_key = params.get('--access-key-id') or environ.get('AWS_ACCESS_KEY_ID')
    if params.get('--secret-key-file'):
        with open(params.get('--secret-key-file')) as f:
            secret_key = f.read().strip()
    else:
        secret_key = params.get('--secret-key') or environ.get('AWS_SECRET_ACCESS_KEY')
    return access_key, secret_key


def get_zone(con, zone_name, vpc):

    res = con.get_all_hosted_zones()
    zones = res['ListHostedZonesResponse']['HostedZones']
    zone_list = [z for z in zones
                    if z['Config']['PrivateZone'] == (u'true' if vpc.get('is_private') else u'false')
                        and z['Name'] == zone_name + '.']

    for zone in zone_list:
        data = {}
        data['id'] = zone.get('Id','').replace('/hostedzone/', '')
        data['name'] = zone.get('Name')
        if vpc.get("is_private"):
            z = con.get_hosted_zone(data.get('id'))
            z_vpc_id = z.get('GetHostedZoneResponse',{}).get('VPCs',{}).get('VPC',{}).get('VPCId','')
            if z_vpc_id == vpc.get('id'):
                return data
            else:
                continue
        else:
            return data
    else:
        return None


def create_zone(con, zone_name, vpc):
    con.create_hosted_zone(domain_name=zone_name,
                           private_zone=vpc.get('is_private'),
                           vpc_region=vpc.get('region'),
                           vpc_id=vpc.get('id'),
                           comment='autogenerated by route53-transfer @ {}'.format(ts))
    return get_zone(con, zone_name, vpc)


def inflate_csv_record(all_recs):
    """
    Converts a CSV zone record into a route53.record.Record instance

    Example:

        NAME,TYPE,VALUE,TTL,REGION,WEIGHT,SETID,FAILOVER,EVALUATE_HEALTH
        db.example.com.,A,1.2.3.4,300,,,production-db,,

    :param all_recs: All CSV records for a single resource
    :return: Record
    """
    record = Record()

    # List of CSV fields as parsed from a single line of a zone dump
    csv_fields = all_recs[0]

    record.name = csv_fields[0]
    record.type = csv_fields[1]

    if csv_fields[2].startswith('ALIAS'):
        _, alias_hosted_zone_id, alias_dns_name = csv_fields[2].split(':')
        record.alias_hosted_zone_id = alias_hosted_zone_id
        record.alias_dns_name = alias_dns_name
    else:
        record.resource_records = [r[2] for r in all_recs]
        record.ttl = csv_fields[3]

    record.region = csv_fields[4] or None
    record.weight = csv_fields[5] or None
    record.identifier = csv_fields[6] or None
    record.failover = csv_fields[7] or None

    try:
        if csv_fields[8] == 'True':
            record.alias_evaluate_target_health = True
        elif csv_fields[8] == 'False':
            record.alias_evaluate_target_health = False
        else:
            record.alias_evaluate_target_health = None
    except IndexError as e:
        print("Invalid record: ", csv_fields)
        raise e

    return record


def group_values(lines):
    records = []
    for _, records in itertools.groupby(lines, lambda row: row[0:2]):
        for __, by_value in itertools.groupby(records, lambda row: row[-3:]):
            recs = list(by_value)  # consume the iterator so we can grab positionally
            record = inflate_csv_record(recs)

            yield record


def read_lines(file_in):
    reader = csv.reader(file_in)
    lines = list(reader)
    if lines[0][0] == 'NAME':
        lines = lines[1:]
    return lines


def read_records(file_in):
    return list(group_values(read_lines(file_in)))


def skip_apex_soa_ns(zone, records):
    for record in records:
        if record.name == zone['name'] and record.type in ['SOA', 'NS']:
            continue
        else:
            yield record


def comparable(records):
    return {ComparableRecord(record) for record in records}


def get_file(filename, mode):
    ''' Get a file-like object for a filename and mode.

        If filename is "-" return one of stdin or stdout.
    '''
    if filename == '-':
        if mode.startswith('r'):
            return sys.stdin
        elif mode.startswith('w'):
            return sys.stdout
        else:
            raise ValueError('Unknown mode "{}"'.format(mode))
    else:
        return open(filename, mode)


def load(con, zone_name, file_in, **kwargs):
    ''' Send DNS records from input file to Route 53.

        Arguments are Route53 connection, zone name, vpc info, and file to open for reading.
    '''
    dry_run = kwargs.get('dry_run', False)
    vpc = kwargs.get('vpc', {})

    zone = get_zone(con, zone_name, vpc)
    if not zone:
        if dry_run:
            print('CREATE ZONE:', zone_name)
        else:
            zone = create_zone(con, zone_name, vpc)

    existing_records = comparable(skip_apex_soa_ns(zone, con.get_all_rrsets(zone['id'])))
    desired_records = comparable(skip_apex_soa_ns(zone, read_records(file_in)))

    to_delete = existing_records.difference(desired_records)
    to_add = desired_records.difference(existing_records)

    if to_add or to_delete:
        changes = ResourceRecordSets(con, zone['id'])
        for record in to_delete:
            change = changes.add_change('DELETE', **record.to_change_dict())
            print ("DELETE", record.name, record.type)
            for value in record.resource_records:
                change.add_value(value)
        for record in to_add:
            change = changes.add_change('CREATE', **record.to_change_dict())
            print ("CREATE", record.name, record.type, record.resource_records)
            for value in record.resource_records:
                change.add_value(value)

        if dry_run:
            print ("Dry run requested: no changes are going to be applied")
        else:
            print ("Applying changes...")
            changes.commit()
        print ("Done.")
    else:
        print ("No changes.")


def dump(con, zone_name, fout, **kwargs):
    ''' Receive DNS records from Route 53 to output file.

        Arguments are Route53 connection, zone name, vpc info, and file to open for writing.
    '''
    vpc = kwargs.get('vpc', {})

    zone = get_zone(con, zone_name, vpc)
    if not zone:
        exit_with_error("ERROR: {} zone {} not found!".format('Private' if vpc.get('is_private') else 'Public',
                                                              zone_name))

    out = csv.writer(fout)
    out.writerow(['NAME', 'TYPE', 'VALUE', 'TTL', 'REGION', 'WEIGHT', 'SETID', 'FAILOVER', "EVALUATE_HEALTH"])

    records = list(con.get_all_rrsets(zone['id']))
    for r in records:
        lines = record_to_stringlist(r)
        for line in lines:
            out.writerow(line)

    fout.flush()


def record_to_stringlist(r: Record):
    out_lines = []

    if r.alias_dns_name:
        vals = [':'.join(['ALIAS', r.alias_hosted_zone_id, r.alias_dns_name])]
    else:
        vals = r.resource_records

    for val in vals:
        out_lines.append([
            r.name, r.type, val, r.ttl, r.region, r.weight, r.identifier,
            r.failover, r.alias_evaluate_target_health])

    return out_lines


def up_to_s3(con, file, s3_bucket):
    con.create_bucket(s3_bucket)
    bucket = con.get_bucket(s3_bucket)
    bucket_key = Key(bucket)
    bucket_key.key = file
    bucket_key.set_contents_from_filename(file, num_cb=10)


def run(params):
    access_key, secret_key = get_aws_credentials(params)
    con = route53.connect_to_region('universal', aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    con_s3 = connect_s3(aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    zone_name = params['<zone>']
    filename = params['<file>']

    vpc = {}
    if params.get('--private'):
        vpc['is_private'] = True
        vpc['region'] = params.get('--vpc-region') or environ.get('AWS_DEFAULT_REGION')
        vpc['id'] = params.get('--vpc-id')
        if not vpc.get('region') or not vpc.get('id'):
            exit_with_error("ERROR: Private zones require associated VPC Region and ID "
                            "(--vpc-region, --vpc-id)".format(zone_name))
    else:
        vpc['is_private'] = False

    if params.get('dump'):
        dump(con, zone_name, get_file(filename, 'w'), vpc=vpc)
        if params.get('--s3-bucket'):
            up_to_s3(con_s3, params.get('<file>'), params.get('--s3-bucket'))
    elif params.get('load'):
        dry_run = params.get('--dry-run', False)
        load(con, zone_name, get_file(filename, 'r'), vpc=vpc, dry_run=dry_run)
    else:
        return 1
