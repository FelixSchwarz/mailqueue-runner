# SPDX-License-Identifier: MIT

from datetime import timedelta as TimeDelta

from schwarz.mailqueue.delivery_log import DeliveryEvent, format_delay, format_logfmt


def test_format_logfmt():
    event = DeliveryEvent(
        status = 'sent',
        to     = 'foo@site.example,bar@site.example',
        smtp   = '250 OK "id"\nsecond line',
        via    = 'smtp:mx.site.example',
    )
    expected = r'status=sent      to=foo@site.example,bar@site.example via=smtp:mx.site.example smtp="250 OK \"id\"\nsecond line"'  # noqa: E501
    assert format_logfmt(event) == expected

    failed_event = DeliveryEvent(status='failed', to='foo@site.example', error='')
    assert format_logfmt(failed_event) == 'status=failed    to=foo@site.example error=""'

def test_delivery_event_as_dict():
    event = DeliveryEvent(status='deferred', to='foo@site.example', from_addr='bar@site.example', attempts=2)
    expected = {'status': 'deferred', 'to': 'foo@site.example', 'from': 'bar@site.example', 'attempts': 2}
    assert event.as_dict() == expected

def test_format_delay():
    assert format_delay(TimeDelta(seconds=42)) == '42s'
    assert format_delay(TimeDelta(minutes=10, seconds=59)) == '10m'
    assert format_delay(TimeDelta(hours=2, minutes=5)) == '2h05m'
    assert format_delay(TimeDelta(days=1, hours=3, minutes=10)) == '1d3h'
