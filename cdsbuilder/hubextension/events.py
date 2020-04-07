
import asyncio

from tornado.web import authenticated, HTTPError
from async_generator import aclosing

from jupyterhub.apihandlers.users import SpawnProgressAPIHandler
from jupyterhub.utils import iterate_until

from ..orm import Dashboard


class ProgressDashboardHandler(SpawnProgressAPIHandler):

    @authenticated
    async def get(self, user_name, dashboard_urlname=''):
        self.set_header('Cache-Control', 'no-cache')

        current_user = await self.get_current_user()

        dashboard_user = self.user_from_username(user_name)

        dashboard = self.db.query(Dashboard).filter(Dashboard.urlname==dashboard_urlname).one_or_none()

        if dashboard is None or dashboard_user is None:
            raise HTTPError(404, 'No such dashboard or user')

        if dashboard.user.name != dashboard_user.name:
            raise HTTPError(404, 'Dashboard user {} does not match {}'.format(dashboard.user.name, dashboard_user.name))

        if not dashboard.is_orm_user_allowed(current_user.orm_user):
            raise HTTPError(403, 'User {} not authorized to access dashboard {}'.format(current_user.name, dashboard_user.urlname))
        

        # start sending keepalive to avoid proxies closing the connection
        asyncio.ensure_future(self.keepalive())
        # cases:
        # - spawner already started and ready
        # - spawner not running at all
        # - spawner failed
        # - spawner pending start (what we expect)
        url = 'testurl'
        ready_event = {
            'progress': 100,
            'ready': True,
            'message': "Server ready at {}".format(url),
            'html_message': 'Server ready at <a href="{0}">{0}</a>'.format(url),
            'url': url,
        }
        failed_event = {'progress': 100, 'failed': True, 'message': "Build failed"}


        builders_store = self.settings['cds_builders']

        builder = builders_store[dashboard]

        if builder.ready:
            # spawner already ready. Trigger progress-completion immediately
            self.log.info("Server %s is already started", builder._log_name)
            await self.send_event(ready_event)
            return

        build_future = builder._build_future

        if not builder._build_pending:
            # not pending, no progress to fetch
            # check if spawner has just failed
            f = build_future
            if f and f.done() and f.exception():
                failed_event['message'] = "Build failed: %s" % f.exception()
                await self.send_event(failed_event)
                return
            else:
                raise HTTPError(400, "%s is not starting...", builder._log_name)

        # retrieve progress events from the Spawner
        async with aclosing(
            iterate_until(build_future, builder._generate_progress())
        ) as events:
            try:
                async for event in events:
                    # don't allow events to sneakily set the 'ready' flag
                    if 'ready' in event:
                        event.pop('ready', None)
                    await self.send_event(event)
            except asyncio.CancelledError:
                pass

        # progress finished, wait for spawn to actually resolve,
        # in case progress finished early
        # (ignore errors, which will be logged elsewhere)
        await build_future

        # progress and spawn finished, check if spawn succeeded
        if builder.ready:
            # spawner is ready, signal completion and redirect
            self.log.info("Server %s is ready", builder._log_name)
            await self.send_event(ready_event)
        else:
            # what happened? Maybe spawn failed?
            f = build_future
            if f and f.done() and f.exception():
                failed_event['message'] = "Build failed: %s" % f.exception()
            else:
                self.log.warning(
                    "Server %s didn't start for unknown reason", builder._log_name
                )
            await self.send_event(failed_event)



