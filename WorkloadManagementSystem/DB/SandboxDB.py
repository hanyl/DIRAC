########################################################################
# $Header: /tmp/libdirac/tmp.stZoy15380/dirac/DIRAC3/DIRAC/WorkloadManagementSystem/DB/SandboxDB.py,v 1.11 2008/10/29 17:59:00 atsareg Exp $
########################################################################
""" SandboxDB class is a simple storage using MySQL as a container for
    relatively small sandbox files. The file size is limited to 16MB.
    The following methods are provided

    addLoggingRecord()
    getJobLoggingInfo()
    getWMSTimeStamps()
"""

__RCSID__ = "$Id: SandboxDB.py,v 1.11 2008/10/29 17:59:00 atsareg Exp $"

import re, os, sys, threading
import time, datetime
from types import *

from DIRAC  import gConfig, gLogger, S_OK, S_ERROR
from DIRAC.Core.Base.DB import DB

#############################################################################
class SandboxDB(DB):

  def __init__( self, sandbox_type, maxQueueSize=10 ):
    """ Standard Constructor
    """

    DB.__init__(self,sandbox_type,'WorkloadManagement/SandboxDB',maxQueueSize)

    self.maxSize = gConfig.getValue( self.cs_path+'/MaxSandboxSize', 16 )
    self.maxPartitionSize = gConfig.getValue( self.cs_path+'/MaxPartitionSize', 5 )
    self.maxPartitionSize *= 1024*1024*1024 # in GBs

    self.maxPartitionSize = 100000

    self.lock = threading.Lock()

#############################################################################
  def storeFile(self,jobID,filename,fileString,sandbox):
    """ Store input sandbox ASCII file for jobID with the name filename which
        is given with its string body
    """

    result = self.__getWorkingPartition('InputSandbox')
    if not result['OK']:
      return result
    pTable = result['Value']

    fileSize = len(fileString)
    if fileSize > self.maxSize*1024*1024:
      return S_ERROR('File size too large %.2f MB for file %s' % \
                     (fileSize/1024./1024.,filename))

    # Check that the file does not exist already
    req = "SELECT FileName,Partition FROM %s WHERE JobID=%d AND FileName='%s'" % \
          (sandbox,int(jobID),filename)
    result = self._query(req)
    if not result['OK']:
      return result
    if len(result['Value']) > 0:
      partTable = result['Value'][0][1]
      # Remove the already existing file - overwrite
      gLogger.warn('Overwriting file %s for job %d' % (filename,int(jobID)))
      req = "DELETE FROM %s WHERE JobID=%d AND FileName='%s'" % \
            (sandbox,int(jobID),filename)
      result = self._update(req)
      if not result['OK']:
        return result
      if partTable:
        req = "DELETE FROM %s WHERE JobID=%d AND FileName='%s'" % \
              (partTable,int(jobID),filename)
        result = self._update(req)
        if not result['OK']:
          return result

    inFields = ['JobID','FileName','FileBody','Partition']
    inValues = [jobID,filename,'',pTable]
    result = self._insert(sandbox,inFields,inValues)
    if not result['OK']:
      return result

    inFields = ['JobID','FileName','FileBody','FileSize']
    inValues = [jobID,filename,fileString,len(fileString)]
    result = self._insert(pTable,inFields,inValues)
    return result

  def __getTableSize(self,table):
    """ Get the table size in bytes
    """

    req = "SHOW TABLE STATUS LIKE '%s'" % table
    result = self._query(req)
    if not result['OK']:
      return result

    if not result['Value']:
      return S_ERROR('No result returned from the database')

    size = int(result['Value'][0][6])
    return S_OK(size)

  def __getTableContentsSize(self,table):
    """ Get the table size in bytes
    """

    req = "SELECT SUM(FileSize) FROM %s" % table
    result = self._query(req)
    if not result['OK']:
      return result

    size = int(result['Value'][0][0])
    return S_OK(size)

  def __getCurrentPartition(self,sandbox):
    """ Get the current sandbox partition number
    """

    req = "SELECT PartID FROM %sPartitions" % sandbox
    result = self._query(req)
    if not result['OK']:
      return result

    partID = 0
    if result['Value']:
      partID = int(result['Value'][0][0])
    return S_OK(partID)

  def __getWorkingPartition(self,sandbox):
    """ Get the working partition
    """

    result = self.__getCurrentPartition(sandbox)
    if not result['OK']:
      return result

    sprefix = "IS"
    if sandbox == "OutputSandbox":
      sprefix = "OS"

    partID = result['Value']
    if partID == 0:
      result = self.__createPartition(sandbox)
      if not result['OK']:
        return result
      partID = result['Value']
      return S_OK('%s_%d' % (sprefix,partID))

    result = self.__getTableSize('%s_%d' % (sprefix,partID))
    if not result['OK']:
      return result

    size = result['Value']
    if size > self.maxPartitionSize:
      result = self.__createPartition(sandbox)
      if not result['OK']:
        return result
      partID = result['Value']

    return S_OK('%s_%d' % (sprefix,partID))

  def __createPartition(self,sandbox):
    """ Create new snadbox partition
    """

    sprefix = "IS"
    if sandbox == "OutputSandbox":
      sprefix = "OS"
    self.lock.acquire()
    req = "INSERT INTO %sPartitions (CreationDate,LastUpdate) VALUES (UTC_TIMESTAMP(),UTC_TIMESTAMP())" % sandbox
    result = self._getConnection()
    if result['OK']:
      connection = result['Value']
    else:
      return S_ERROR('Failed to get connection to MySQL: '+result['Message'])
    res = self._update(req,connection)
    if not res['OK']:
      self.lock.release()
      return res
    req = "SELECT LAST_INSERT_ID();"
    res = self._query(req,connection)
    self.lock.release()
    partID = int(res['Value'][0][0])

    req = """CREATE TABLE %s_%d(
    JobID INTEGER NOT NULL,
    FileName VARCHAR(255) NOT NULL,
    FileBody LONGBLOB NOT NULL,
    FileSize INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (JobID,FileName)
) ENGINE=MyISAM MAX_ROWS=150000 AVG_ROW_LENGTH=150000;
""" % (sprefix,partID)

    result = self._update(req)
    if not result['OK']:
      return S_ERROR('Failed to create new Sandbox partition')

    return S_OK(partID)

#############################################################################
  def getSandboxFile(self,jobID,filename,sandbox):
    """ Store input sandbox ASCII file for jobID with the name filename which
        is given with its string body
    """

    req = "SELECT FileBody,Partition FROM %s WHERE JobID=%d AND FileName='%s'" % \
          (sandbox, int(jobID), filename)

    result = self._query(req)
    if not result['OK']:
      return result
    if len(result['Value']) == 0:
      return S_ERROR('Sandbox file not found')

    body = result['Value'][0][0]
    partition = result['Value'][0][1]
    if body and not partition:
      return S_OK(body)

    if partition:
      req = "SELECT FileBody FROM %s WHERE JobID=%d AND FileName='%s'" % \
            (partition, int(jobID), filename)
      result = self._query(req)
      if not result['OK']:
        return result
      if len(result['Value']) == 0:
        return S_ERROR('Sandbox file not found')
      body = result['Value'][0][0]
      return S_OK(body)
    else:
      return S_ERROR('Sandbox file not found')

#############################################################################
  def getFileNames(self,jobID,sandbox):
    """ Get file names for a given job in a given sandbox
    """

    req = "SELECT FileName FROM %s WHERE JobID=%d" % (sandbox,int(jobID))
    result = self._query(req)
    if not result['OK']:
      return result
    if len(result['Value']) == 0:
      return S_ERROR('No files found for job %d' % int(jobID))

    fileList = [ x[0] for x in result['Value']]
    return S_OK(fileList)

#############################################################################
  def removeJob(self,jobID,sandbox):
    """ Remove all the files belonging to the given job
    """

    req = "SELECT FileName,Partition FROM %s WHERE JobID=%d" % (sandbox,int(jobID))
    result = self._query(req)
    if not result['OK']:
      return result

    if not result['Value']:
      return S_OK()

    for fname,partition in result['Value']:
      req = "DELETE FROM %s WHERE JobID=%d" % (partition,int(jobID))
      result = self._update(req)
      if not result['OK']:
        gLogger.warn('Failed to remove files for job %d' % jobID)
        return result

    req = "DELETE FROM %s WHERE JobID=%d" % (sandbox,int(jobID))
    result = self._update(req)
    if not result['OK']:
      gLogger.warn('Failed to remove files for job %d' % jobID)
      return result

    gLogger.info('Removed files for job %d' % jobID)
    return S_OK()