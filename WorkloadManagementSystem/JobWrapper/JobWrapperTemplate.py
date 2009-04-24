import sys
sys.path.insert(0,"@SITEPYTHON@")
from DIRAC.Core.Base import Script
Script.parseCommandLine()
##############################################################################################################################
# $Id: JobWrapperTemplate.py,v 1.15 2009/04/24 17:05:03 rgracian Exp $
# Generated by JobAgent version: @SIGNATURE@ for Job @JOBID@ on @DATESTRING@.
##############################################################################################################################

from DIRAC.WorkloadManagementSystem.JobWrapper.JobWrapper   import JobWrapper
from DIRAC.WorkloadManagementSystem.Client.JobReport        import JobReport
from DIRAC.Core.DISET.RPCClient                             import RPCClient
from DIRAC                                                  import S_OK, S_ERROR, gConfig, gLogger

import os

os.umask(022)

class JobWrapperError(Exception):
  def __init__(self, value):
    self.value = value
  def __str__(self):
    return str(self.value)

jobReport = None

def rescheduleFailedJob(jobID,message):
  try:
    global jobReport

    gLogger.warn('Failure during %s' %(message))

    #Setting a job parameter does not help since the job will be rescheduled,
    #instead set the status with the cause and then another status showing the
    #reschedule operation.

    if not jobReport:
      gLogger.info('Creating a new JobReport Object')
      jobReport = JobReport(int(jobID),'JobWrapperTemplate')

    jobReport.setJobStatus( 'Failed', message, sendFlag = False )
    jobReport.setApplicationStatus( 'Failed %s ' % message, sendFlag = False )
    jobReport.setJobStatus( minor = 'ReschedulingJob', sendFlag = False )

    # We must send Job States and Parameters before it gets reschedule
    jobReport.sendStoredStatusInfo()
    jobReport.sendStoredJobParameters()

    gLogger.info('Job will be rescheduled after exception during execution of the JobWrapper')

    jobManager  = RPCClient('WorkloadManagement/JobManager')
    result = jobManager.rescheduleJob(int(jobID))
    if not result['OK']:
      gLogger.warn(result)

    return
  except Exception,x:
    gLogger.exception('JobWrapperTemplate failed to reschedule Job')
    return

def execute ( arguments ):

  global jobReport

  jobID = arguments['Job']['JobID']
  os.environ['JOBID'] = jobID
  jobID = int(jobID)

  if arguments.has_key('WorkingDirectory'):
    wdir = os.path.expandvars(arguments['WorkingDirectory'])
    if os.path.isdir(wdir):
      os.chdir(wdir)
    else:
      try:
        os.makedirs(wdir)
        if os.path.isdir(wdir):
          os.chdir(wdir)
      except Exception, x:
        gLogger.exception('JobWrapperTemplate could not create working directory')
        rescheduleFailedJob(jobID,'Could Not Create Working Directory')
        return

  root = arguments['CE']['Root']
  jobReport = JobReport(jobID,'JobWrapper')

  try:
    job = JobWrapper( jobID, jobReport )
    job.initialize(arguments)
  except Exception, x:
    gLogger.exception('JobWrapper failed the initialization phase')
    rescheduleFailedJob(jobID,'Job Wrapper Initialization')
    job.sendWMSAccounting('Failed','Job Wrapper Initialization')
    return

  if arguments['Job'].has_key('InputSandbox'):
    jobReport.sendStoredStatusInfo()
    jobReport.sendStoredJobParameters()

    try:
      result = job.transferInputSandbox(arguments['Job']['InputSandbox'])
      if not result['OK']:
        gLogger.warn(result['Message'])
        raise JobWrapperError(result['Message'])
    except Exception, x:
      gLogger.exception('JobWrapper failed to download input sandbox')
      rescheduleFailedJob(jobID,'Input Sandbox Download')
      job.sendWMSAccounting('Failed','Input Sandbox Download')
      return
  else:
    gLogger.verbose('Job has no InputSandbox requirement')

  jobReport.sendStoredStatusInfo()
  jobReport.sendStoredJobParameters()

  if arguments['Job'].has_key('InputData'):
    if arguments['Job']['InputData']:
      try:
        result = job.resolveInputData(arguments['Job']['InputData'])
        if not result['OK']:
          gLogger.warn(result['Message'])
          raise JobWrapperError(result['Message'])
      except Exception, x:
        message = 'JobWrapper failed to resolve input data with exception:  \n%s' %(str(x))
        gLogger.warn(message)
        gLogger.exception()
        rescheduleFailedJob(jobID,'Input Data Resolution')
        job.sendWMSAccounting('Failed','Input Data Resolution')
        return
    else:
      gLogger.verbose('Job has a null InputData requirement:')
      gLogger.verbose(arguments)
  else:
    gLogger.verbose('Job has no InputData requirement')

  jobReport.sendStoredStatusInfo()
  jobReport.sendStoredJobParameters()

  try:
    result = job.execute(arguments)
    if not result['OK']:
      gLogger.error(result['Message'])
      raise JobWrapperError(result['Message'])
  except Exception, x:
    if str(x) == '0':
      gLogger.verbose('JobWrapper exited with status=0 after execution')
      pass
    else:
      message = 'Job failed in execution phase with exception:  \n%s' %(str(x))
      gLogger.warn(message)
      gLogger.exception()
      jobReport.setJobStatus('Failed',str(x),sendFlag=False)
      jobParam = jobReport.setJobParameter('Error Message',message,sendFlag=False)
      if not jobParam['OK']:
        gLogger.warn(jobParam)
      job.sendFailoverRequest('Failed','Exception During Execution')
      return

  if arguments['Job'].has_key('OutputSandbox') or arguments['Job'].has_key('OutputData'):
    try:
      result = job.processJobOutputs(arguments)
      if not result['OK']:
        gLogger.warn(result['Message'])
        raise JobWrapperError(result['Message'])
    except Exception, x:
      message = 'JobWrapper failed to process output files with exception: \n%s' %(str(x))
      gLogger.warn(message)
      gLogger.exception()
      jobReport.setJobParameter('Error Message',message,sendFlag=False)
      jobReport.setJobStatus('Failed','Uploading Job Outputs',sendFlag=False)
      job.sendFailoverRequest('Failed','Uploading Job Outputs')
      return
  else:
    gLogger.verbose('Job has no OutputData or OutputSandbox requirement')

  try:
    job.finalize(arguments)
  except Exception, x:
    message = 'JobWrapper failed the finalization phase with exception: \n%s' %(str(x))
    gLogger.warn(message)
    gLogger.exception()
    return

###################### Note ##############################
# The below arguments are automatically generated by the #
# JobAgent, do not edit them.                            #
##########################################################
try:
  jobArgs = eval("""@JOBARGS@""")
  execute( jobArgs )
  jobReport.sendStoredStatusInfo()
  jobReport.sendStoredJobParameters()
except:
  try:
    jobReport.sendStoredStatusInfo()
    jobReport.sendStoredJobParameters()
  except:
    pass
