"""unblock_all.py

ReadUntil implementation that will only unblock reads. This should result in
a read length histogram that has very short peaks (~280-580bp) as these are the
smallest chunks that we can acquire. If you are not seeing these peaks, the
`split_reads_after_seconds` parameter in the configuration file may need to be
edited to 0.2-0.4:
(<MinKNOW_folder>/ont-python/lib/python2.7/site-packages/bream4/configuration)
"""
# Core imports
import functools
import logging
import sys
import os
import time
from timeit import default_timer as timer

# Read Until imports
from ru.arguments import BASE_ARGS
from ru.utils import print_args, get_device
from ru.utils import send_message, Severity
from ru.read_until_client import RUClient
from ru.read_until_client import AccumulatingReadCache
from ru.basecall import Mapper as CustomMapper
from ru.basecall import CPUCaller as Caller




_help = "Call read chunks with DeepNano really?"
_cli = BASE_ARGS

def med_mad(x, factor=1.4826):
    """
    Calculate signal median and median absolute deviation
    """
    med = np.median(x)
    mad = np.median(np.absolute(x - med)) * factor
    return med, mad

def rescale_signal(signal):
    print (signal)
    print(type(signal))
    signal = signal.astype(np.float32)
    med, mad = med_mad(signal)
    signal -= med
    signal /= mad
    return signal


def deepnano_analysis(client, duration, batch_size=512, throttle=0.1, unblock_duration=0.1):
    """Analysis function

    Parameters
    ----------
    client : read_until_api.ReadUntilClient
        An instance of the ReadUntilClient object
    duration : int
        Time to run for, in seconds
    batch_size : int
        The number of reads to be retrieved from the ReadUntilClient at a time
    throttle : int or float
        The number of seconds interval between requests to the ReadUntilClient
    unblock_duration : int or float
        Time, in seconds, to apply unblock voltage

    Returns
    -------
    None
    """
    run_duration = time.time() + duration
    caller_kwargs=None
    caller = Caller()
    decided_reads = {}

    logger = logging.getLogger(__name__)
    send_message(client.connection, "ReadFish sending Unblock All Messages for DeepNano. All reads will be prematurely truncated. This will affect a live sequencing run.",
                 Severity.WARN)
    while client.is_running and time.time() < run_duration:

        r = 0
        t0 = timer()

        for (channel,read_number),read_id,seq,readinbatch,qual in caller.basecall_minknow(
            reads=client.get_read_chunks(batch_size=batch_size, last=True),
            signal_dtype=client.signal_dtype,
            decided_reads=decided_reads,
        ):
            if channel == 456:
                logger.info(f"{read_id} {len(seq):>5,}")
                print (channel,read_id,len(seq))
                print(seq)

        """
        for r, (channel, read) in enumerate(
                client.get_read_chunks(
                    batch_size=batch_size,
                    last=True,
                ),
                start=1,
        ):
            # pass
            
            client.unblock_read(channel, read.number, read_id=read.id, duration=unblock_duration)
            client.stop_receiving_read(channel, read.number)


            print (caller.call_raw_signal(rescale_signal(read.raw_data)))
        """
        t1 = timer()
        if r:
            logger.info("Taking {:.6f} for {} reads".format(t1-t0, r))
        # limit the rate at which we make requests
        if t0 + throttle > t1:
            time.sleep(throttle + t0 - t1)
    else:
        send_message(client.connection, "ReadFish Unblock All Disconnected.", Severity.WARN)
        logger.info("Finished analysis of reads as client stopped.")


def main():
    sys.exit(
        "This entry point is deprecated, please use 'readfish unblock-all' instead"
    )


def run(parser, args):
    # TODO: Move logging config to separate configuration file
    # TODO: use setup_logger here instead?
    # set up logging to file for DEBUG messages and above
    logging.basicConfig(
        level=logging.DEBUG,
        # TODO: args.log_format
        format="%(levelname)s %(asctime)s %(name)s %(message)s",
        filename=args.log_file,
        filemode="w",
    )

    # define a Handler that writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)

    # set a format which is simpler for console use
    formatter = logging.Formatter(args.log_format)
    console.setFormatter(formatter)

    # add the handler to the root logger
    logging.getLogger("").addHandler(console)

    # Start by logging sys.argv and the parameters used
    logger = logging.getLogger("Manager")
    # logger = setup_logger(__name__, args.log_format, log_file=args.log_file, level=logging.INFO)
    logger.info(" ".join(sys.argv))
    print_args(args, logger=logger)

    position = get_device(args.device)

    read_until_client = RUClient(
        mk_host=position.host,
        mk_port=position.description.rpc_ports.insecure,
        filter_strands=True,
        cache_size=args.cache_size,
        cache_type=AccumulatingReadCache,
    )

    read_until_client.run(
        **{"first_channel": args.channels[0], "last_channel": args.channels[-1]}
        #** {"first_channel": 456, "last_channel": 456}
    )

    try:
        deepnano_analysis(
            client=read_until_client,
            duration=args.run_time,
            batch_size=args.batch_size,
            throttle=args.throttle,
            unblock_duration=args.unblock_duration,
        )
    except KeyboardInterrupt:
        pass
    finally:
        read_until_client.reset()


if __name__ == "__main__":
    main()