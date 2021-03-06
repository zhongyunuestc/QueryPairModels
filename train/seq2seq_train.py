import tensorflow as tf
import sys
sys.path.append('.')
from utils.data_reader import InputPipe
from utils.trainer import SingleboxTrainer
from models.seq2seq import Seq2Seq
import os
import time
from datetime import datetime
from utils.param import FLAGS
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
#os.environ["CUDA_VISIBLE_DEVICES"] = '0,1'
def train():
    with tf.Graph().as_default(), tf.device('/cpu:0'):
        tf.gfile.Copy(FLAGS.input_previous_model_path + "/" + FLAGS.decoder_vocab_file, FLAGS.output_model_path + "/" + FLAGS.decoder_vocab_file, overwrite=True)
        global_step = tf.train.get_or_create_global_step()
        inc_step = tf.assign_add(global_step,1)
        #Training setting
        if FLAGS.use_mstf_ops:
            train_input_pipe = InputPipe([FLAGS.input_training_data_path + "/" + i for i in tf.gfile.ListDirectory(FLAGS.input_training_data_path)], FLAGS.batch_size, FLAGS.num_epochs, 2, "",False)
            auc_eval_pipe = InputPipe(FLAGS.input_validation_data_path + "/label_data.txt", FLAGS.eval_batch_size,1,3,"",False) if FLAGS.auc_evaluation else None
            bleu_eval_pipe = InputPipe(FLAGS.input_validation_data_path + "/bleu_data.txt", FLAGS.eval_batch_size,1,2,"",False) if FLAGS.bleu_evaluation else None
        else:
            train_input_pipe = InputPipe([FLAGS.input_training_data_path + "/" + i for i in tf.gfile.ListDirectory(FLAGS.input_training_data_path)], FLAGS.batch_size, FLAGS.num_epochs, 2, "0",False)
            auc_eval_pipe = InputPipe(FLAGS.input_validation_data_path + "/label_data.txt", FLAGS.eval_batch_size,1,3,"0",False) if FLAGS.auc_evaluation else None
            bleu_eval_pipe = InputPipe(FLAGS.input_validation_data_path + "/bleu_data.txt", FLAGS.eval_batch_size,1,2,"0",False) if FLAGS.bleu_evaluation else None
        model = Seq2Seq()
        trainer = SingleboxTrainer(model,inc_step,train_input_pipe,auc_eval_pipe, bleu_eval_pipe)
        summary_op = tf.summary.merge_all()

        config = tf.ConfigProto()
        config.gpu_options.allow_growth = True
        config.allow_soft_placement=True
        saver = tf.train.Saver(max_to_keep = FLAGS.max_model_to_keep, name = 'model_saver')
        with tf.Session(config = config) as session:
            summ_writer = tf.summary.FileWriter(FLAGS.log_dir, session.graph)
            #Load Pretrain
            session.run(tf.local_variables_initializer())
            session.run(tf.global_variables_initializer())
            session.run(tf.tables_initializer())
            session.run(train_input_pipe.iterator.initializer)
            ckpt = tf.train.get_checkpoint_state(FLAGS.input_previous_model_path)
            if ckpt and ckpt.model_checkpoint_path:
                saver.restore(session, ckpt.model_checkpoint_path)
                print("Load Model From ", ckpt.model_checkpoint_path)
            else:
                print("No Initial Model Found.")
            trainer.start_time = time.time()
            while True:
                try:
                    _,avg_loss,total_weight,step,summary = session.run(trainer.train_ops() + [summary_op])
                    #print(step)
                    if step % FLAGS.log_frequency == 1:
                        summ_writer.add_summary(summary,step)
                        trainer.print_log(total_weight,step,avg_loss)
                    if step % FLAGS.checkpoint_frequency == 1:
                        if FLAGS.auc_evaluation:
                            trainer.eval(step,session,'auc')
                        if FLAGS.bleu_evaluation:
                            trainer.eval(step,session,'bleu')
                        if trainer.improved():
                            saver.save(session, FLAGS.output_model_path + "/seq2seq_model", global_step=step)
                        elif trainer.early_stop():
                            print("\nEarly stop")
                            break
                except tf.errors.OutOfRangeError:
                    print("End of training.")
                    break
            if not trainer.early_stop():
                saver.save(session, FLAGS.output_model_path + "/" + "seq2seq_model_final", global_step = step)


def predict():
    outputter = tf.gfile.GFile(FLAGS.output_model_path + "/" + FLAGS.result_filename, mode = "w")
    predict_mode = tf.contrib.learn.ModeKeys.INFER if FLAGS.mode == 'predict' else tf.contrib.learn.ModeKeys.EVAL
    model = Seq2Seq()
    if predict_mode == tf.contrib.learn.ModeKeys.INFER:
        if FLAGS.use_mstf_ops:
            pred_pipe = InputPipe(FLAGS.input_validation_data_path, FLAGS.eval_batch_size,1,FLAGS.test_fields,"",True)
        else:
            pred_pipe = InputPipe(FLAGS.input_validation_data_path, FLAGS.eval_batch_size,1,FLAGS.test_fields,"0",True)
        trainer = SingleboxTrainer(model, None, None, None, pred_pipe)
    else:
        if FLAGS.use_mstf_ops:
            red_pipe = InputPipe(FLAGS.input_validation_data_path, FLAGS.eval_batch_size,1,FLAGS.test_fields,"",True)
        else:
            pred_pipe = InputPipe(FLAGS.input_validation_data_path, FLAGS.eval_batch_size,1,FLAGS.test_fields,"0",True)
        trainer = SingleboxTrainer(model, None, None, pred_pipe, None)
    scope = tf.get_variable_scope()
    scope.reuse_variables()
    saver = tf.train.Saver()
    config = tf.ConfigProto()
    config.gpu_options.allow_growth = True
    config.allow_soft_placement=True
    with tf.Session(config = config) as sess:
        sess.run(tf.local_variables_initializer())
        sess.run(tf.tables_initializer())
        sess.run(tf.global_variables_initializer())
        ckpt = tf.train.get_checkpoint_state(FLAGS.input_previous_model_path)
        if ckpt and ckpt.model_checkpoint_path:
            saver.restore(sess, ckpt.model_checkpoint_path)
            print("Load model from ", ckpt.model_checkpoint_path)
        else:
            print("No initial model found.")
        trainer.predict(sess, predict_mode, outputter)
    outputter.close()


if __name__ == '__main__':
    #Create folders
    if not tf.gfile.Exists(FLAGS.log_dir):
        tf.gfile.MakeDirs(FLAGS.log_dir)
    if not tf.gfile.Exists(FLAGS.output_model_path):
        tf.gfile.MakeDirs(FLAGS.output_model_path)
    if FLAGS.mode == 'train':
        train()
    elif FLAGS.mode == 'predict' or FLAGS.mode == 'eval':
        predict()
    

