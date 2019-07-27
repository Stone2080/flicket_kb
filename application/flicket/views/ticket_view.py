#! usr/bin/python3
# -*- coding: utf-8 -*-
#
# Flicket - copyright Paul Bourne: evereux@gmail.com

import datetime

from flask import render_template, redirect, url_for, g, request, flash
from flask_login import login_required
from flask_babel import gettext

from . import flicket_bp
from application import app, db
from application.flicket.forms.flicket_forms import ReplyForm, SubscribeUser
from application.flicket.models.flicket_models import FlicketTicket
from application.flicket.models.flicket_models import FlicketStatus
from application.flicket.models.flicket_models import FlicketPost
from application.flicket.models.flicket_models import FlicketSubscription
from application.flicket.models.flicket_user import FlicketUser
from application.flicket.scripts.flicket_functions import add_action
from application.flicket.scripts.flicket_functions import block_quoter
from application.flicket.scripts.flicket_upload import UploadAttachment
from application.flicket.scripts.email import FlicketMail
from application.flicket.scripts.subscriptions import subscribe_user


# view ticket details
@flicket_bp.route(app.config['FLICKET'] + 'ticket_view/<ticket_id>/', methods=['GET', 'POST'])
@flicket_bp.route(app.config['FLICKET'] + 'ticket_view/<ticket_id>/<int:page>/', methods=['GET', 'POST'])
@login_required
def ticket_view(ticket_id, page=1):
    # todo: make sure underscores aren't allowed in usernames as it breaks markdown?

    # is ticket number legitimate
    ticket = FlicketTicket.query.filter_by(id=ticket_id).first()

    if not ticket:
        flash(gettext('Cannot find ticket: "%(value)s"', value=ticket_id), category='warning')
        return redirect(url_for('flicket_bp.tickets'))

    # find all replies to ticket.
    replies = FlicketPost.query.filter_by(ticket_id=ticket_id).order_by(FlicketPost.date_added.asc())

    # get reply id's
    post_rid = request.args.get('post_rid')
    ticket_rid = request.args.get('ticket_rid')

    form = ReplyForm()
    subscribers_form = SubscribeUser()

    # add subscribed user
    if subscribers_form.validate_on_submit():
        user = FlicketUser.query.filter_by(username=subscribers_form.username.data).first()
        if subscribe_user(ticket, user):
            flash(gettext('User subscribed.'))
        else:
            flash(gettext('User already subsribed.'))

    # add reply post
    if form.submit.data and form.validate_on_submit():
        # upload file if user has selected one and the file is in accepted list of
        files = request.files.getlist("file")
        upload_attachments = UploadAttachment(files)
        if upload_attachments.are_attachements():
            upload_attachments.upload_files()

        new_reply = FlicketPost(
            ticket=ticket,
            user=g.user,
            date_added=datetime.datetime.now(),
            content=form.content.data,
        )

        if ticket.status_id != form.status.data:
            ticket.status_id = form.status.data
            add_action(action=ticket.current_status.status, ticket=ticket)

        if ticket.ticket_priority_id != form.priority.data:
            ticket.ticket_priority_id = form.priority.data
            add_action(action=ticket.ticket_priority.priority, ticket=ticket)

        db.session.add(new_reply)

        # add files to database.
        upload_attachments.populate_db(new_reply)

        # change ticket status to open if closed.
        if ticket.current_status.status.lower() == 'closed':
            ticket_open = FlicketStatus.query.filter_by(status='Open').first()
            ticket.current_status = ticket_open

        # subscribe to the ticket
        if not ticket.is_subscribed(g.user):
            subscribe = FlicketSubscription(
                ticket=ticket,
                user=g.user
            )
            db.session.add(subscribe)

        # add count of 1 to users total posts.
        g.user.total_posts += 1

        db.session.commit()

        # send email notification
        mail = FlicketMail()
        mail.reply_ticket(ticket=ticket, reply=new_reply)

        flash(gettext('You have replied to ticket %(value_1)s: %(value_2)s.', value_1=ticket.id_zfill,
                      value_2=ticket.title), category="success")

        # if the reply has been submitted for closure.
        if form.submit_close.data:
            return redirect(url_for('flicket_bp.change_status', ticket_id=ticket.id, status='Closed'))

        return redirect(url_for('flicket_bp.ticket_view', ticket_id=ticket_id))

    # get post id and populate contents for auto quoting
    if post_rid:
        query = FlicketPost.query.filter_by(id=post_rid).first()
        reply_contents = gettext("%(value_1)s wrote on %(value_2)s\r\n\r\n%(value_3)s",
                                 value_1=query.user.name,
                                 value_2=query.date_added,
                                 value_3=query.content)
        form.content.data = block_quoter(reply_contents)
    if ticket_rid:
        reply_contents = gettext("%(value_1)s wrote on %(value_2)s\r\n\r\n%(value_3)s",
                                 value_1=ticket.user.name,
                                 value_2=ticket.date_added,
                                 value_3=ticket.content)
        form.content.data = block_quoter(reply_contents)

    replies = replies.paginate(page, app.config['posts_per_page'])

    form.status.data = ticket.status_id

    title = gettext('View Ticket')

    return render_template('flicket_view.html',
                           title=title,
                           ticket=ticket,
                           form=form,
                           subscribers_form=subscribers_form,
                           replies=replies,
                           page=page)
