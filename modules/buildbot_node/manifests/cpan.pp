#/etc/puppet/modules/buildbot_node/manifests/cpan.pp

include cpan

# buildbot cpan  class for the build slaves.
class buildbot_node::cpan (

  $cpan_modules,

) {

  require stdlib
  require buildbot_node

  #define cpan modules
  define buildbot_node::install_modules ($module = $title) {
    cpan { $module :
      ensure    => present,
    }
  }

  buildbot_node::install_modules   { $cpan_modules: }


}
