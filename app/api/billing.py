"""Stripe billing routes — subscription management."""
from datetime import datetime, timezone

import stripe
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from app import db

billing_bp = Blueprint("billing", __name__)


def _init_stripe():
    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]


@billing_bp.route("/checkout", methods=["POST"])
@login_required
def create_checkout():
    _init_stripe()

    # Create or retrieve Stripe customer
    if not current_user.stripe_customer_id:
        customer = stripe.Customer.create(email=current_user.email)
        current_user.stripe_customer_id = customer.id
        db.session.commit()

    session = stripe.checkout.Session.create(
        customer=current_user.stripe_customer_id,
        payment_method_types=["card"],
        line_items=[{
            "price": current_app.config["STRIPE_PRICE_ID"],
            "quantity": 1,
        }],
        mode="subscription",
        success_url=request.host_url + "dashboard?subscribed=true",
        cancel_url=request.host_url + "dashboard?cancelled=true",
    )

    return jsonify({"checkout_url": session.url})


@billing_bp.route("/portal", methods=["POST"])
@login_required
def customer_portal():
    _init_stripe()

    if not current_user.stripe_customer_id:
        return jsonify({"error": "No subscription found"}), 400

    session = stripe.billing_portal.Session.create(
        customer=current_user.stripe_customer_id,
        return_url=request.host_url + "dashboard",
    )
    return jsonify({"portal_url": session.url})


@billing_bp.route("/webhook", methods=["POST"])
def webhook():
    _init_stripe()
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    webhook_secret = current_app.config["STRIPE_WEBHOOK_SECRET"]

    try:
        event = stripe.Webhook.construct_event(payload, sig, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return "Invalid signature", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        _handle_checkout_completed(session)

    elif event["type"] == "customer.subscription.updated":
        sub = event["data"]["object"]
        _handle_subscription_updated(sub)

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        _handle_subscription_deleted(sub)

    return "", 200


def _handle_checkout_completed(session):
    from app.models import User
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    user = User.query.filter_by(stripe_customer_id=customer_id).first()
    if user:
        user.stripe_subscription_id = subscription_id
        user.is_subscribed = True
        db.session.commit()


def _handle_subscription_updated(sub):
    from app.models import User
    customer_id = sub.get("customer")
    user = User.query.filter_by(stripe_customer_id=customer_id).first()
    if user:
        status = sub.get("status")
        user.is_subscribed = status in ("active", "trialing")
        if sub.get("current_period_end"):
            user.subscription_end = datetime.fromtimestamp(sub["current_period_end"], tz=timezone.utc)
        db.session.commit()


def _handle_subscription_deleted(sub):
    from app.models import User
    customer_id = sub.get("customer")
    user = User.query.filter_by(stripe_customer_id=customer_id).first()
    if user:
        user.is_subscribed = False
        user.stripe_subscription_id = None
        db.session.commit()
