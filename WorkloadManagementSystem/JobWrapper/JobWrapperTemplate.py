import sys
sys.path.insert(0,"@SITEPYTHON@")
from DIRAC.Core.Base import Script
Script.parseCommandLine()
##############################################################################################################################
# $Id: JobWrapperTemplate.py,v 1.24 2009/05/04 04:47:25 rgracian Exp $
# Generated by JobAgent version: @SIGNATURE@ for Job @JOBID@ on @DATESTRING@.
##############################################################################################################################

from DIRAC.WorkloadManagementSystem.JobWrapper.JobWrapper   import JobWrapper
from DIRAC.WorkloadManagementSystem.Client.JobReport        import JobReport
from DIRAC.Core.DISET.RPCClient                             import RPCClient
from DIRAC.FrameworkSystem.Client.NotificationClient        import NotificationClient

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
    import DIRAC
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

    # Send mail to debug errors
    mailAddress = DIRAC.alarmMail
    site        = gConfig.getValue('/LocalSite/Site', '')
    subject     = 'Job rescheduled at %s' % site
    ret         = systemCall(0,'hostname')
    wn          = ret['Value'][1]
    msg         = 'Job %s rescheduled at %s, wn=%s\n' % ( jobID, site, wn )
    msg        += message

    NotificationClient().sendMail(mailAddress,subject,msg,fromAddress="lhcb-dirac@cern.ch",localAttempt=False)

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
        return 1

  root = arguments['CE']['Root']
  jobReport = JobReport(jobID,'JobWrapper')

  try:
    job = JobWrapper( jobID, jobReport )
    job.initialize(arguments)
  except Exception, x:
    gLogger.exception('JobWrapper failed the initialization phase')
    rescheduleFailedJob(jobID,'Job Wrapper Initialization')
    job.sendWMSAccounting('Failed','Job Wrapper Initialization')
    return 1

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
      return 1
  else:
    gLogger.verbose('Job has no InputSandbox requirement')

  jobReport.sendStoredStatusInfo()
  jobReport.sendStoredJobParameters()

  if arguments['Job'].has_key('InputData'):
    if arguments['Job']['InputData']:
      try:
        result = job.resolveInputData()
        if not result['OK']:
          gLogger.warn(result['Message'])
          raise JobWrapperError(result['Message'])
      except Exception, x:
        gLogger.exception('JobWrapper failed to resolve input data')
        rescheduleFailedJob(jobID,'Input Data Resolution')
        job.sendWMSAccounting('Failed','Input Data Resolution')
        return 1
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
      gLogger.exception('Job failed in execution phase')
      jobReport.setJobParameter('Error Message',str(x),sendFlag=False)
      jobReport.setJobStatus('Failed','Exception During Execution',sendFlag=False)
      job.sendFailoverRequest('Failed','Exception During Execution')
      return 1

  if arguments['Job'].has_key('OutputSandbox') or arguments['Job'].has_key('OutputData'):
    try:
      result = job.processJobOutputs(arguments)
      if not result['OK']:
        gLogger.warn(result['Message'])
        raise JobWrapperError(result['Message'])
    except Exception, x:
      gLogger.exception('JobWrapper failed to process output files')
      jobReport.setJobParameter('Error Message',str(x),sendFlag=False)
      jobReport.setJobStatus('Failed','Uploading Job Outputs',sendFlag=False)
      job.sendFailoverRequest('Failed','Uploading Job Outputs')
      return 2
  else:
    gLogger.verbose('Job has no OutputData or OutputSandbox requirement')

  try:
    # Failed jobs will return 1 / successful jobs will return 0
    return job.finalize(arguments)
  except Exception, x:
    gLogger.exception('JobWrapper failed the finalization phase')
    return 2

###################### Note ##############################
# The below arguments are automatically generated by the #
# JobAgent, do not edit them.                            #
##########################################################
ret = -3
try:
  jobArgs = eval("""@JOBARGS@""")
  ret = execute( jobArgs )
  jobReport.sendStoredStatusInfo()
  jobReport.sendStoredJobParameters()
except Exception,x:
  try:
    gLogger.exception()
    jobReport.sendStoredStatusInfo()
    jobReport.sendStoredJobParameters()
    ret = -1
  except Exception,x:
    gLogger.exception()
    ret = -2

sys.exit(ret)
