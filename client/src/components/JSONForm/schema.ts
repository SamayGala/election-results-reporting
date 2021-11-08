import * as Yup from 'yup'

const jsonSchema = Yup.object().shape({
  json: Yup.mixed().required('You must upload a file'),
})

export default jsonSchema