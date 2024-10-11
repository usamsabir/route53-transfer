"""
Unit tests for the route53 change batch computation
"""
from unittest.mock import Mock

from boto.route53.record import Record

from route53_transfer.app import changes_to_r53_updates, is_valid, record_short_summary
from tests.helpers import to_comparable


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

def test_valid_localhost_ipv4():
    # Purpose: Verify that the localhost IPv4 address is correctly identified as valid
    # Expected behavior: is_valid should return True for '127.0.0.1'
    key = 'ipv4'
    value = '127.0.0.1'
    result = is_valid(key, value)
    assert result == True, f"Expected True but got {result}"

def test_valid_normal_ipv4():
    # Purpose: Verify that a standard IPv4 address is correctly identified as valid
    # Expected behavior: is_valid should return True for '192.168.1.1'
    key = 'ipv4'
    value = '192.168.1.1'
    result = is_valid(key, value)
    assert result == True, f"Expected True but got {result}"

def test_invalid_ipv4_out_of_range():
    # Purpose: Verify that an IPv4 address with an octet out of valid range is identified as invalid
    # Expected behavior: is_valid should return False for '192.168.1.256' (256 is out of range)
    key = 'ipv4'
    value = '192.168.1.256'
    result = is_valid(key, value)
    assert result == False, f"Expected False but got {result}"

def test_invalid_ipv4_leading_zero():
    # Purpose: Verify that an IPv4 address with a leading zero in an octet is identified as invalid
    # Expected behavior: is_valid should return False for '192.168.01.1' (leading zero in third octet)
    key = 'ipv4'
    value = '192.168.01.1'
    result = is_valid(key, value)
    assert result == False, f"Expected False but got {result}"

def test_valid_localhost_ipv6():
    # Purpose: Verify that the localhost IPv6 address is correctly identified as valid
    # Expected behavior: is_valid should return True for '::1'
    key = 'ipv6'
    value = '::1'
    result = is_valid(key, value)
    assert result == True, f"Expected True but got {result}"

def test_valid_normal_ipv6():
    # Purpose: Verify that a standard full IPv6 address is correctly identified as valid
    # Expected behavior: is_valid should return True for '2001:0db8:85a3:0000:0000:8a2e:0370:7334'
    key = 'ipv6'
    value = '2001:0db8:85a3:0000:0000:8a2e:0370:7334'
    result = is_valid(key, value)
    assert result == True, f"Expected True but got {result}"

def test_valid_ipv6_omitted_zeros():
    # Purpose: Verify that an IPv6 address with omitted leading zeros is correctly identified as valid
    # Expected behavior: is_valid should return True for '2001:db8:85a3:0:0:8a2e:370:7334'
    key = 'ipv6'
    value = '2001:db8:85a3:0:0:8a2e:370:7334'
    result = is_valid(key, value)
    assert result == True, f"Expected True but got {result}"

def test_invalid_ipv6_too_many_groups():
    # Purpose: Verify that an IPv6 address with too many groups is identified as invalid
    # Expected behavior: is_valid should return False for '2001:0db8:85a3:0000:0000:8a2e:0370:7334:1234' (9 groups instead of 8)
    key = 'ipv6'
    value = '2001:0db8:85a3:0000:0000:8a2e:0370:7334:1234'
    result = is_valid(key, value)
    assert result == False, f"Expected False but got {result}"

def test_record_short_summary_alias_ipv4():
    # Purpose: Verify that record_short_summary correctly handles an alias record with an invalid IPv4 address
    # Expected behavior: record_short_summary should return an empty string when the content IPv4 is invalid
    mock_record = Mock()
    mock_record.name = "example.com."
    mock_record.type = "A"
    mock_record.alias_dns_name = "192.0.2.1"
    mock_record.alias_hosted_zone_id = "Z2FDTNDATAQYW2"
    mock_record.ttl = 300

    # Note: The IPv4 address in content has a leading zero, which should make it invalid
    content = {'ipv4': '192.168.0.1'}
    result = record_short_summary(mock_record, content)
    expected = ""
    assert result == expected, f"Expected '{expected}' but got '{result}'"

def test_record_short_summary_alias_ipv4():
    # Purpose: Verify that record_short_summary correctly handles an alias record with a valid IPv4 address
    # Expected behavior: record_short_summary should return the correct summary string for a valid IPv4 address
    mock_record = Mock()
    mock_record.name = "example.com."
    mock_record.type = "A"
    mock_record.alias_dns_name = "192.0.2.1"
    mock_record.alias_hosted_zone_id = "Z2FDTNDATAQYW2"
    mock_record.ttl = 300

    # Note: This is a valid IPv4 address
    content = {'ipv4': '127.255.255.255'}

    result = record_short_summary(mock_record, content)
    expected = "example.com. A ALIAS:Z2FDTNDATAQYW2:192.0.2.1 300"
    assert result == expected, f"Expected '{expected}' but got '{result}'"
