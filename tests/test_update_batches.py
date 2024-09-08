"""
Unit tests for the route53 change batch computation
"""

from boto.route53.record import Record

from route53_transfer.app import changes_to_r53_updates
from helpers import to_comparable


TEST_ZONE_ID = 1
TEST_ZONE_NAME = "test.dev"
TEST_ZONE = {"id": TEST_ZONE_ID, "name": TEST_ZONE_NAME}


def test_empty_changes_list():
    zone = TEST_ZONE
    r53_change_batches = changes_to_r53_updates(zone, [])
    assert len(r53_change_batches) == 0


def test_single_change():
    zone = TEST_ZONE

    ptr = Record()
    ptr.type = "A"
    ptr.name = "server1."
    ptr.resource_records = ["1.2.3.4"]

    change_operations = [
        {"zone": zone,
         "operation": "CREATE",
         "record": to_comparable(ptr)}
    ]

    r53_change_batches = changes_to_r53_updates(zone, change_operations)
    assert len(r53_change_batches) == 1


def test_alias_change_in_separate_updates():
    zone = TEST_ZONE

    srv1 = Record()
    srv1.type = "A"
    srv1.name = "server1"
    srv1.resource_records = ["1.2.3.4"]

    srv2_alias = Record()
    srv2_alias.type = "A"
    srv2_alias.name = "server2"
    srv2_alias.alias_hosted_zone_id = str(TEST_ZONE_ID)
    srv2_alias.alias_dns_name = "server1"
    srv2_alias.alias_evaluate_target_health = False

    change_operations = [
        {"zone": zone,
         "operation": "CREATE",
         "record": to_comparable(srv2_alias)},

        {"zone": zone,
         "operation": "CREATE",
         "record": to_comparable(srv1)},
    ]

    r53_change_batches = changes_to_r53_updates(zone, change_operations)
    assert len(r53_change_batches) == 2, \
        "Two update batches expected since there is a record that is an alias"

    first_update = r53_change_batches[0]
    change_dict = first_update.changes[0]["change_dict"]
    assert change_dict["name"] == "server1"
    assert change_dict["alias_dns_name"] is None

    second_update = r53_change_batches[1]
    change_dict = second_update.changes[0]["change_dict"]
    assert change_dict["name"] == "server2"
    assert change_dict["alias_dns_name"] == "server1"


def test_two_chained_aliases_resolved_in_three_updates():
    zone = TEST_ZONE

    srv1 = Record()
    srv1.type = "A"
    srv1.name = "server1"
    srv1.resource_records = ["1.2.3.4"]

    srv2_alias = Record()
    srv2_alias.type = "A"
    srv2_alias.name = "server2"
    srv2_alias.alias_hosted_zone_id = str(TEST_ZONE_ID)
    srv2_alias.alias_dns_name = "server1"
    srv2_alias.alias_evaluate_target_health = False

    srv3_alias = Record()
    srv3_alias.type = "A"
    srv3_alias.name = "server3"
    srv3_alias.alias_hosted_zone_id = str(TEST_ZONE_ID)
    srv3_alias.alias_dns_name = "server2"
    srv3_alias.alias_evaluate_target_health = False

    change_operations = [
        {"zone": zone,
         "operation": "CREATE",
         "record": to_comparable(srv2_alias)},

        {"zone": zone,
         "operation": "CREATE",
         "record": to_comparable(srv3_alias)},

        {"zone": zone,
         "operation": "CREATE",
         "record": to_comparable(srv1)},
    ]

    r53_change_batches = changes_to_r53_updates(zone, change_operations)
    assert len(r53_change_batches) == 3, \
        "Three update batches expected since there are two record aliases in a chain"

    first_update = r53_change_batches[0]
    change_dict = first_update.changes[0]["change_dict"]
    assert change_dict["name"] == "server1"
    assert change_dict["alias_dns_name"] is None

    second_update = r53_change_batches[1]
    change_dict = second_update.changes[0]["change_dict"]
    assert change_dict["name"] == "server2"
    assert change_dict["alias_dns_name"] == "server1"

    third_update = r53_change_batches[2]
    change_dict = third_update.changes[0]["change_dict"]
    assert change_dict["name"] == "server3"
    assert change_dict["alias_dns_name"] == "server2"

def test_valid_ipv4():
    zone = {'ipv4': '192.168.1.1'}
    result = changes_to_r53_complex_parser(zone)
    assert result == True, f"Expected True but got {result}"

def test_invalid_ipv4_out_of_range():
    zone = {'ipv4': '256.256.256.256'}
    result = changes_to_r53_complex_parser(zone)
    assert result == False, f"Expected False but got {result}"

def test_valid_domain():
    zone = {'domain': 'example.com'}
    result = changes_to_r53_complex_parser(zone)
    assert result == True, f"Expected True but got {result}"

def test_invalid_domain_leading_hyphen():
    zone = {'domain': '-example.com'}
    result = changes_to_r53_complex_parser(zone)
    assert result == False, f"Expected False but got {result}"

def test_incomplete_ipv4():
    zone = {'ipv4': '192.168.1'}
    result = changes_to_r53_complex_parser(zone)
    assert result == False, f"Expected False but got {result}"

def test_domain_with_trailing_dot():
    zone = {'domain': 'example.com.'}
    result = changes_to_r53_complex_parser(zone)
    assert result == False, f"Expected False but got {result}"

def test_valid_localhost_ipv4():
    zone = {'ipv4': '127.0.0.1'}
    result = changes_to_r53_complex_parser(zone)
    assert result == True, f"Expected True but got {result}"

def test_domain_with_consecutive_dots():
    zone = {'domain': 'example..com'}
    result = changes_to_r53_complex_parser(zone)
    assert result == False, f"Expected False but got {result}"

def test_ipv4_with_leading_zeroes():
    zone = {'ipv4': '192.168.001.001'}
    result = changes_to_r53_complex_parser(zone)
    assert result == False, f"Expected True but got {result}"

def test_domain_with_invalid_character():
    zone = {'domain': '!example.com'}
    result = changes_to_r53_complex_parser(zone)
    assert result == False, f"Expected False but got {result}"