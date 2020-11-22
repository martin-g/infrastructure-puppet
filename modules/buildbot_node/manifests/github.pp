##/etc/puppet/modules/buildbot_node/manifests/init.pp

class buildbot_node::github (

  $github_rsa     = '',
  $github_rsa_pub = '',

)  {

  require buildbot_node

  file {

  "/home/${buildbot_node::username}/.ssh/id_rsa_github":
    require => File["/home/${buildbot_node::username}/.ssh"],
    path    => "/home/${buildbot_node::username}/.ssh/id_rsa_github",
    owner   => $buildbot_node::username,
    group   => $buildbot_node::groupname,
    mode    => '0600',
    content => template('buildbot_node/ssh/id_rsa_github.erb');

  "/home/${buildbot_node::username}/.ssh/id_rsa_github.pub":
    require => File["/home/${buildbot_node::username}/.ssh"],
    path    => "/home/${buildbot_node::username}/.ssh/id_rsa_github.pub",
    owner   => $buildbot_node::username,
    group   => $buildbot_node::groupname,
    mode    => '0644',
    content => template('buildbot_node/ssh/id_rsa_github.pub.erb');
  }

}

