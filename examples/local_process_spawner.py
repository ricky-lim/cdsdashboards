c.JupyterHub.db_url = 'sqlite:///examples/sqlitedbs/local_process_spawner.sqlite'

c.JupyterHub.authenticator_class = 'jupyterhub.auth.DummyAuthenticator'

from jupyterhub.spawner import LocalProcessSpawner

class SameUserSpawner(LocalProcessSpawner):

    def make_preexec_fn(self, name):
        return lambda: None

    def user_env(self, env):
        path = '/Users/dan/Dev/cdsdashboards/examples/local_process_folder/%s' % self.user.name

        try:
            os.mkdir(path)
        except OSError:
            print('Failed to create directory: %s' % path)
       
        return env

    def _notebook_dir_default(self):
        return f'/Users/dan/Dev/cdsdashboards/examples/local_process_folder/{self.user.name}'

from cdsdashboards.hubextension.spawners.variablemixin import VariableMixin, MetaVariableMixin

class VariableSameUserSpawner(SameUserSpawner, VariableMixin, metaclass=MetaVariableMixin):
    pass

c.JupyterHub.spawner_class = VariableSameUserSpawner


c.CDSDashboardsConfig.builder_class = 'cdsdashboards.builder.processbuilder.ProcessBuilder'

c.LocalProcessSpawner.notebook_dir = '/Users/dan/Dev/cdsdashboards/examples/local_process_folder/{username}'

c.Spawner.start_timeout = 6000

c.Spawner.debug = True

c.Authenticator.admin_users = {'dan'}

c.ConfigurableHTTPProxy.debug = True

c.JupyterHub.allow_named_servers = True

import os
dirname = os.path.dirname(__file__)

#c.CDSDashboardsConfig.extra_presentation_types = ['custom-panel', 'unavailable']

c.VariableMixin.extra_presentation_launchers = {
    'streamlit': {
        'env': {'JUPYTERHUB_COOKIE_OPTIONS': '{"SameSite": "None", "Secure": true}'}
    }
}


c.CDSDashboardsConfig.show_source_git = True
c.CDSDashboardsConfig.show_source_servers = False

c.CDSDashboardsConfig.conda_envs = ['env1', 'env2', 'cds']
#c.CDSDashboardsConfig.allow_custom_conda_env = True

#c.CDSDashboardsConfig.default_allow_all = True

#c.VariableMixin.voila_template = 'materialstream'


#c.CDSDashboardsConfig.spawn_allow_group = 'spawners-group'


c.VariableMixin.proxy_last_activity_interval = 10

c.VariableMixin.proxy_force_alive = True


from cdsdashboards.app import CDS_TEMPLATE_PATHS
from cdsdashboards.hubextension import cds_extra_handlers

c.JupyterHub.template_paths = CDS_TEMPLATE_PATHS
c.JupyterHub.extra_handlers = cds_extra_handlers



import os

#  Generate certs:
# openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout myjupyterhub.net/jupyterhub.key -out myjupyterhub.net/jupyterhub.crt

## Path to SSL certificate file for the public facing interface of the proxy
#
#  When setting this, you should also set ssl_key
c.JupyterHub.ssl_cert = os.environ['SSL_CERT']

## Path to SSL key file for the public facing interface of the proxy
#
#  When setting this, you should also set ssl_cert
c.JupyterHub.ssl_key = os.environ['SSL_KEY']

c.JupyterHub.internal_ssl = False

c.JupyterHub.bind_url = 'https://0.0.0.0:443'

#c.ConfigurableHTTPProxy.command = ['configurable-http-proxy', '--no-x-forward']


c.JupyterHub.redirect_to_server = False

c.JupyterHub.default_url = '/hub/dashboards'
