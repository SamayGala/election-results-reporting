/* eslint-disable jsx-a11y/label-has-associated-control */
import React, { useState } from 'react'
import { Formik, FormikProps } from 'formik'
import styled from 'styled-components'
import { HTMLSelect, FileInput, H4 } from '@blueprintjs/core'
import FormWrapper from '../Atoms/Form/FormWrapper'
import FormButton from '../Atoms/Form/FormButton'
import schema from './schema'
import { ErrorLabel, SuccessLabel } from '../Atoms/Form/_helpers'
import FormSection, { FormSectionDescription } from '../Atoms/Form/FormSection'

enum FileProcessingStatus {
  READY_TO_PROCESS = 'READY_TO_PROCESS',
  PROCESSING = 'PROCESSING',
  PROCESSED = 'PROCESSED',
  ERRORED = 'ERRORED',
}

export interface IFileInfo {
  file: {
    name: string
    uploadedAt: string
  } | null
  processing: {
    status: FileProcessingStatus
    startedAt: string | null
    completedAt: string | null
    error: string | null
  } | null
}

export const Select = styled(HTMLSelect)`
  margin-top: 5px;
`

interface IValues {
  json: File | null
}

interface IProps {
  jsonFile: IFileInfo
  uploadJSONFile: (json: File) => Promise<boolean>
  deleteJSONFile?: () => Promise<boolean>
  title?: string
  description: string
  sampleFileLink: string
  enabled: boolean
}

const JSONFile: React.FC<IProps> = (props: IProps) => {
  // Force the form to reset every time props.jsonFile changes
  // E.g. if we upload or delete a file
  // See https://reactjs.org/blog/2018/06/07/you-probably-dont-need-derived-state.html#recap
  // eslint-disable-next-line @typescript-eslint/no-use-before-define
  return <JSONFileForm key={Date.now()} {...props} />
}

const JSONFileForm = ({
  jsonFile,
  uploadJSONFile,
  deleteJSONFile,
  title,
  description,
  sampleFileLink,
  enabled,
}: IProps) => {
  const { file, processing } = jsonFile
  const isProcessing = !!(processing && !processing.completedAt)
  const [isEditing, setIsEditing] = useState<boolean>(!file || isProcessing)

  return (
    <Formik
      initialValues={{ json: isProcessing ? new File([], file!.name) : null }}
      validationSchema={schema}
      validateOnBlur={false}
      onSubmit={async (values: IValues) => {
        if (values.json) {
          await uploadJSONFile(values.json)
        }
      }}
    >
      {({
        handleSubmit,
        setFieldValue,
        values,
        touched,
        errors,
        handleBlur,
        isSubmitting,
      }: FormikProps<IValues>) => (
        <form>
          <FormWrapper>
            <FormSection>
              {title && <H4>{title}</H4>}
              <FormSectionDescription>
                {description}
                {sampleFileLink && (
                  <>
                    <br />
                    <br />
                    <a
                      href={sampleFileLink}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      (Click here to view a sample file in the correct format.)
                    </a>
                  </>
                )}
              </FormSectionDescription>
            </FormSection>
            <FormSection>
              {isEditing ? (
                <>
                  <FileInput
                    inputProps={{
                      accept: '.json',
                      name: 'json',
                    }}
                    onInputChange={e => {
                      setFieldValue(
                        'json',
                        (e.currentTarget.files && e.currentTarget.files[0]) ||
                          undefined
                      )
                    }}
                    hasSelection={!!values.json}
                    text={values.json ? values.json.name : 'Select a JSON...'}
                    onBlur={handleBlur}
                    disabled={isSubmitting || isProcessing || !enabled}
                    fill
                  />
                  {errors.json && touched.json && (
                    <ErrorLabel>{errors.json}</ErrorLabel>
                  )}
                </>
              ) : (
                <>
                  <p>
                    <strong>Current file:</strong> {file!.name}
                  </p>
                  {processing && processing.error && (
                    <ErrorLabel>{processing.error}</ErrorLabel>
                  )}
                  {processing &&
                    processing.status === FileProcessingStatus.PROCESSED && (
                      <SuccessLabel>
                        Upload successfully completed at{' '}
                        {new Date(`${processing.completedAt}`).toLocaleString()}
                        .
                      </SuccessLabel>
                    )}
                </>
              )}
            </FormSection>
            <div>
              {isEditing ? (
                <FormButton
                  type="submit"
                  intent="primary"
                  onClick={handleSubmit}
                  loading={isSubmitting || isProcessing}
                  disabled={!enabled}
                >
                  Upload File
                </FormButton>
              ) : (
                // We give these buttons a key to make sure React doesn't reuse
                // the submit button for one of them.
                <>
                  <FormButton
                    key="replace"
                    onClick={() => setIsEditing(true)}
                    disabled={!enabled}
                  >
                    Replace File
                  </FormButton>
                  {deleteJSONFile && (
                    <FormButton
                      key="delete"
                      onClick={deleteJSONFile}
                      disabled={!enabled}
                    >
                      Delete File
                    </FormButton>
                  )}
                </>
              )}
            </div>
          </FormWrapper>
        </form>
      )}
    </Formik>
  )
}

export default JSONFile
