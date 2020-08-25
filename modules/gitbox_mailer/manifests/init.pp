#/etc/puppet/modules/gitbox_mailer/manifests/init.pp

class gitbox_mailer (
  $service_name   = 'gitbox-mailer',
  $shell          = '/bin/bash',
  $service_ensure = 'running',
  $username       = 'root',
  $group          = 'root',
  $statsurl       = '',
)
{

  
  require python
  
  if !defined(Python::Pip['asfpy']) {
    python::pip {
      'asfpy' :
        ensure   => latest;
    }
  }
  if !defined(Python::Pip['pyyaml']) {
    python::pip {
      'pyyaml' :
        ensure   => present;
    }
  }
  if !defined(Python::Pip['ezt']) {
    python::pip {
      'ezt' :
        ensure   => present;
    }
  }

  file {
    '/usr/local/etc/gitbox-mailer':
      ensure => directory,
      mode   => '0755',
      owner  => $username,
      group  => $group;
    '/var/run/gitbox-mailer':
      ensure => directory,
      mode   => '0755',
      owner  => 'www-data',
      group  => 'www-data';
    '/usr/local/etc/gitbox-mailer/gitbox-mailer.py':
      mode   => '0755',
      owner  => $username,
      group  => $group,
      source => 'puppet:///modules/gitbox_mailer/gitbox-mailer.py';
    '/usr/local/etc/gitbox-mailer/email_template.ezt':
      mode   => '0644',
      owner  => $username,
      group  => $group,
      source => 'puppet:///modules/gitbox_mailer/email_template.ezt';
    }
    # Set up systemd on first init
    -> file {
      '/lib/systemd/system/gitbox-mailer.service':
        mode   => '0644',
        owner  => 'root',
        group  => 'root',
        source => "puppet:///modules/gitbox_mailer/gitbox-mailer.${::operatingsystem}";
    }
    -> exec { 'gitbox-mailer-systemd-reload':
      command     => 'systemctl daemon-reload',
      path        => [ '/usr/bin', '/bin', '/usr/sbin' ],
      refreshonly => true,
    }
    -> service { $service_name:
        ensure    => $service_ensure,
        subscribe => [
          File['/usr/local/etc/gitbox-mailer/gitbox-mailer.py']
        ]
    }
    cron { 'fetch_lists':
      ensure  => present,
      command => "curl $statsurl --output /x1/gitbox/mailinglists.json > /dev/null 2>&1",
      user    => root,
      minute  => '*/10'
    }
}
