from typing import Protocol
from ..security import fail


class PaymentProvider(Protocol):
    def create_checkout(
        self, tenant_id: str, plan_id: str, idempotency_key: str
    ) -> dict: ...
    def verify_callback(self, headers: dict, body: bytes) -> dict: ...


class DisabledPaymentProvider:
    def create_checkout(self, *args, **kwargs):
        fail("PAYMENT_NOT_ENABLED", "当前为开放期，在线收费尚未启用", 503)

    def verify_callback(self, *args, **kwargs):
        fail("PAYMENT_NOT_ENABLED", "支付渠道尚未启用", 503)
