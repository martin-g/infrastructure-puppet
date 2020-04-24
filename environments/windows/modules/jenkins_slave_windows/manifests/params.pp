#/environments/windows/modules/jenkins_slave_windows/manifests/params.pp

class jenkins_slave_windows::params (

  $user_password    = '',
  $ant = ['apache-ant-1.9.13','apache-ant-1.8.4','apache-ant-1.10.5'], # lint:ignore:140chars
  $chromedriver = ['2.29'],
  $geckodriver = ['0.16.1','0.18.0','0.23.0'],
  $gpg4win = ['3.1.5'],
  $gradle = ['3.5','4.3','4.3.1'],
  $graphviz = ['2.38'],
  $iedriver = ['2.53.1','3.4.0'],
  $jdk = ['jdk1.5.0_22-32','jdk1.5.0_22-64','jdk1.6.0_30','jdk1.8.0_152','jdk9.0','jdk9.0.1','jdk10_46','jdk11-ea+28','jdk12-ea+33','jdk13-ea+30','jdk14-ea+6','jdk15-ea+13'], # lint:ignore:140chars
  $maven = ['apache-maven-2.0.10','apache-maven-2.0.9','apache-maven-2.2.1','apache-maven-3.0.2','apache-maven-3.0.4','apache-maven-3.0.5','apache-maven-3.1.1','apache-maven-3.2.5','apache-maven-3.3.9','apache-maven-3.5.4','apache-maven-3.6.0','apache-maven-3.6.2','apache-maven-3.6.3'], # lint:ignore:140chars
  $nant = ['0.92'],
  $forrest = ['0.9'],
) {}
