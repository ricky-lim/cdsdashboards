from concurrent.futures import ThreadPoolExecutor
import functools

import docker
from docker.errors import APIError
from docker.utils import kwargs_from_env
from traitlets import Dict, Unicode, Any
from tornado import gen, ioloop
from tornado.log import app_log
from datetime import datetime

from jupyterhub.user import User

from ..util import maybe_future
from cdsbuilder.builder.builders import Builder, BuildException


class DockerBuilder(Builder):

    user = Any()

    @property
    def client(self):
        """single global client instance"""
        cls = self.__class__
        if cls._client is None:
            kwargs = {"version": "auto"}
            if self.tls_config:
                kwargs["tls"] = docker.tls.TLSConfig(**self.tls_config)
            kwargs.update(kwargs_from_env())
            kwargs.update(self.client_kwargs)
            client = docker.APIClient(**kwargs)
            cls._client = client
        return cls._client

    tls_config = Dict(
        config=True,
        help="""Arguments to pass to docker TLS configuration.
        See docker.client.TLSConfig constructor for options.
        """,
    )

    client_kwargs = Dict(
        config=True,
        help="Extra keyword arguments to pass to the docker.Client constructor.",
    )

    _client = None

    def _docker(self, method, *args, **kwargs):
        """wrapper for calling docker methods
        to be passed to ThreadPoolExecutor
        """
        m = getattr(self.client, method)
        return m(*args, **kwargs)

    def docker(self, method, *args, **kwargs):
        """Call a docker method in a background thread
        returns a Future
        """
        fn = functools.partial(self._docker, method, *args, **kwargs)
        return ioloop.IOLoop.current().run_in_executor(self._executor, fn)

    _executor = None

    @property
    def executor(self):
        """single global executor"""
        cls = self.__class__
        if cls._executor is None:
            cls._executor = ThreadPoolExecutor(1)
        return cls._executor

    repo_prefix = Unicode(default_value='cdsuser').tag(config=True)

    async def start(self, dashboard, db):
        """Start the dashboard

        Returns:
          (str, int): the (ip, port) where the Hub can connect to the server.

        """

        app_log.info('Starting start function')

        self.event_queue.put_nowait({'progress': 10, 'message': 'Starting builder'})

        self._build_pending = True

        source_spawner = dashboard.source_spawner

        app_log.debug('source_spawner {}'.format(source_spawner))

        object_id = source_spawner.state.get('object_id',None)

        app_log.debug('Docker object_id is {}'.format(object_id))

        if object_id is None:
            raise BuildException('No docker object specified in spawner state')

        i_c_future = self.docker('inspect_container', object_id)

        #i_c_future = maybe_future(i_c_future)

        source_container = await i_c_future

        if source_container is None:
            raise BuildException('No docker object returned as source container')

        # Commit image of current server

        reponame = '{}/{}'.format(self.repo_prefix, dashboard.urlname)

        tag = datetime.today().strftime('%Y%m%d-%H%M%S')

        image_name = '{}:{}'.format(reponame, tag)

        app_log.info('Committing Docker image {}'.format(image_name))

        dockerfile_changes="\n".join([
            'CMD ["voila-entrypoint.sh"]',
            'ENV JUPYTERHUB_GROUP {}'.format(dashboard.groupname),
            'ENV JUPYTERHUB_ANYONE {}'.format(dashboard.allow_all and '1' or '0')
        ])

        await self.docker('commit', object_id, repository=reponame, tag=tag, changes=dockerfile_changes)

        self.log.info('Finished commit of Docker image {}:{}'.format(reponame, tag))

        for i in range(8):
            self.log.debug('Waiting in builder {}'.format(i))
            self.event_queue.put_nowait({'progress': 60, 'message': 'Waiting in builder {}'.format(i)})
            await gen.sleep(1)

        ### Start a new server

        new_server_name = '{}-{}'.format(dashboard.urlname, tag)

        dashboard_user = User(dashboard.user)

        if not self.allow_named_servers:
            raise BuildException(400, "Named servers are not enabled.")
        if (
            self.named_server_limit_per_user > 0
            and new_server_name not in dashboard_user.orm_spawners
        ):
            named_spawners = list(dashboard_user.all_spawners(include_default=False))
            if self.named_server_limit_per_user <= len(named_spawners):
                raise BuildException(
                    "User {} already has the maximum of {} named servers."
                    "  One must be deleted before a new server can be created".format(
                        dashboard_user.name, self.named_server_limit_per_user
                    ),
                )
        spawner = dashboard_user.spawners[new_server_name] # Could be orm_spawner or Spawner wrapper

        if spawner.ready:
            # include notify, so that a server that died is noticed immediately
            # set _spawn_pending flag to prevent races while we wait
            spawner._spawn_pending = True
            try:
                state = await spawner.poll_and_notify()
            finally:
                spawner._spawn_pending = False

        new_server_options = {'image': image_name}

        return (new_server_name, new_server_options)
        
    allow_named_servers = True # TODO take from main app config
    named_server_limit_per_user = 10

    async def stop(self, now=False):
        """Stop the single-user server

        If `now` is False (default), shutdown the server as gracefully as possible,
        e.g. starting with SIGINT, then SIGTERM, then SIGKILL.
        If `now` is True, terminate the server immediately.

        The coroutine should return when the single-user server process is no longer running.

        Must be a coroutine.
        """
        raise NotImplementedError(
            "Override in subclass. Must be a Tornado gen.coroutine."
        )

    async def poll(self):
        pass
