import time
import gevent
from copy import copy
from decorator import decorator

from urllib2 import URLError
from httplib import BadStatusLine

from exception import InterruptLocust

class RequestStatsAdditionError(Exception):
    pass

class RequestStats(object):
    requests = {}
    request_observers = []
    total_num_requests = 0
    global_max_requests = None

    def __init__(self, name):
        self.name = name
        self.num_reqs = 0
        self.num_reqs_per_sec = {}
        self.num_failures = 0
        
        self.total_response_time = 0
        self.min_response_time = None
        self.max_response_time = 0
        
        self._requests = []

    def log(self, response_time, failure=False):
        RequestStats.total_num_requests += 1
        
        self.num_reqs += 1
        self.total_response_time += response_time

        self.num_reqs_per_sec.setdefault(response_time, 0)
        self.num_reqs_per_sec[response_time] += 1

        if not failure:
            if self.min_response_time is None:
                self.min_response_time = response_time
                
            self.min_response_time = min(self.min_response_time, response_time)
            self.max_response_time = max(self.max_response_time, response_time)
            
            self._requests.insert(0, response_time)
            if len(self._requests) >= 2000:
                self._requests = self._requests[0:1000]
        else:
            self.num_failures += 1

    @property
    def avg_response_time(self):
        return self.total_response_time / self.num_reqs
    
    @property
    def median_response_time(self):
        return median(self._requests[0:1000])
    
    @property
    def reqs_per_sec(self):
        timestamp = int(time.time())
        reqs = [self.num_reqs_per_sec.get(t, 0) for t in range(timestamp - 10, timestamp)]
        return avg(reqs)
    
    def __add__(self, other):
        if self.name != other.name:
            raise RequestStatsAdditionError("Trying to add two RequestStats objects of different names (%s and %s)" % (self.name, other.name))
        
        new = RequestStats(other.name)
        new.num_reqs = self.num_reqs + other.num_reqs
        new.num_failures = self.num_failures + other.num_failures
        new.total_response_time = self.total_response_time + other.total_response_time
        new.min_response_time = min(self.min_response_time, other.min_response_time) or other.min_response_time
        new.max_response_time = max(self.max_response_time, other.max_response_time)
        
        new.num_reqs_per_sec = copy(self.num_reqs_per_sec)
        for key in other.num_reqs_per_sec:
            new.num_reqs_per_sec[key] = new.num_reqs_per_sec.setdefault(key, 0) + other.num_reqs_per_sec[key]
        return new
    
    def to_dict(self):
        return {
            'num_reqs': self.num_reqs,
            'num_failures': self.num_failures,
            'avg': self.avg_response_time,
            'min': self.min_response_time,
            'max': self.max_response_time,
            'req_per_sec': self.reqs_per_sec
        }

    def __str__(self):
        return " %-40s %7d %12s %7d %7d %7d  | %7d %7d" % (self.name,
            self.num_reqs,
            "%d(%.2f%%)" % (self.num_failures, (self.num_failures/float(self.num_reqs))*100),
            self.avg_response_time,
            self.min_response_time or 0,
            self.max_response_time,
            self.median_response_time,
            self.reqs_per_sec or 0)

    @classmethod
    def get(cls, name):
        request = cls.requests.get(name, None)
        if not request:
            request = RequestStats(name)
            cls.requests[name] = request
        return request

def avg(values):
    return sum(values, 0.0) / len(values)

def median(values):
    return sorted(values)[len(values)/2] # TODO: Check for odd/even length

def log_request(f):
    def _wrapper(*args, **kwargs):
        name = kwargs.get('name', args[1])
        try:
            if RequestStats.global_max_requests is not None and RequestStats.total_num_requests >= RequestStats.global_max_requests:
                raise InterruptLocust("Maximum number of requests reached")
            start = time.time()
            retval = f(*args, **kwargs)
            response_time = int((time.time() - start) * 1000)
            RequestStats.get(name).log(response_time)
            return retval
        except (URLError, BadStatusLine), e:
            RequestStats.get(name).log(0, True)
    return _wrapper

def print_stats(stats):
    print " %-40s %7s %12s %7s %7s %7s  | %7s %7s" % ('Name', '# reqs', '# fails', 'Avg', 'Min', 'Max', 'Median', 'req/s')
    print "-" * 120
    for r in stats.itervalues():
        print r
    print "-" * 120
    print ""

def stats_printer():
    from core import locust_runner
    while True:
        print_stats(locust_runner.request_stats)
        gevent.sleep(2)