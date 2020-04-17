#!/usr/bin/perl

#  setlock.pl Execute command while holding exclusive lock, with optional wait time
#  Usage:  setlock.pl [-t secs] /path/to/lockfile $command @args

=head1 NOTICE TO MAINTAINERS

Change C<puppet:modules/mail_archives/files/scripts/setlock.pl> and not this file directly.

=cut

use strict;
use warnings FATAL => 'all';
use Fcntl ":flock";

my $timeout = 0;
if ($ARGV[0] eq '-t') {
    shift;
    $timeout=(shift) + 0;
};

my ($lockfile, $command, @args) = @ARGV;

die "Usage: $0 /path/to/lockfile command args"
    unless $lockfile and $command;

open my $fh, "+>>", $lockfile or die "Can't open lockfile $lockfile: $!";
if ($timeout > 0) {
    eval {
        local $SIG{ALRM} = sub { die "Timeout waiting for lock ($timeout)" };
        alarm $timeout;
        flock $fh, LOCK_EX or die "Can't get exclusive lock on $lockfile: $!";
        alarm 0;
    };
    die "$@\n" if ($@);
} else {
	flock $fh, LOCK_EX or die "Can't get exclusive lock on $lockfile: $!";
}

# Lock granted, execute the command
exit system $command, @args;

